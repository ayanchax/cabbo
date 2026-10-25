"""Exercise cleanup entry points without loading production settings or services."""
import ast
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from typing import Optional, Literal
from pydantic import BaseModel
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import column

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from services.trips.temp_trip_service import preserve_temp_trip
from models.financial.payments_enum import ReconciliationStateEnum
from models.trip.trip_enums import TripStatusEnum
from models.policies.refund_enum import PaymentProvider

# Load just the payment models, avoiding unrelated app/settings imports.
_schema_tree = ast.parse((ROOT / "src/models/financial/payments_schema.py").read_text(encoding="utf-8"))
_schema_scope = dict(BaseModel=BaseModel, Optional=Optional, ReconciliationStateEnum=ReconciliationStateEnum, PaymentProvider=PaymentProvider)
for _node in _schema_tree.body:
    if isinstance(_node, ast.ClassDef) and _node.name in {"RazorPayPaymentResponse", "ReconciliationOutcome", "PaymentWebhookNotice"}:
        exec(compile(ast.Module(body=[_node], type_ignores=[]), "payments_schema.py", "exec"), _schema_scope)
ReconciliationOutcome = _schema_scope["ReconciliationOutcome"]
RazorPayPaymentResponse = _schema_scope["RazorPayPaymentResponse"]
PaymentWebhookNotice = _schema_scope["PaymentWebhookNotice"]
_trip_schema_tree = ast.parse((ROOT / "src/models/trip/trip_schema.py").read_text(encoding="utf-8"))
_schema_scope.update(Literal=Literal, TripStatusEnum=TripStatusEnum)
_status_node = next(n for n in _trip_schema_tree.body if isinstance(n, ast.ClassDef) and n.name == "BookingPaymentStatus")
exec(compile(ast.Module(body=[_status_node], type_ignores=[]), "trip_schema.py", "exec"), _schema_scope)
BookingPaymentStatus = _schema_scope["BookingPaymentStatus"]


def load_function(path, name, **dependencies):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name)
    scope = dict(
        AsyncSession=object, Session=object,
        TempTrip=SimpleNamespace(**{name: column(name) for name in ("id", "creator_id", "created_at", "hash")}),
        select=MagicMock(), log=logging.getLogger(__name__),
        preserve_temp_trip=preserve_temp_trip, datetime=datetime,
        ReconciliationStateEnum=ReconciliationStateEnum, Trip=object,
        ReconciliationOutcome=ReconciliationOutcome,
        BookingPaymentStatus=BookingPaymentStatus,
        timedelta=timedelta, timezone=timezone, TTL_MINUTES_DEFAULT=30,
        CabboException=RuntimeError, GENERIC_EXCEPTION="error", UNAUTHORIZED="unauthorized",
        **dependencies,
    )
    exec(compile(ast.Module(body=[node], type_ignores=[]), path, "exec"), scope)
    return scope[name]


def row(metadata):
    return SimpleNamespace(id="booking", payment_provider_metadata=metadata,
                           created_at=datetime.now(timezone.utc) - timedelta(hours=2))


def async_db(rows):
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    result.scalars.return_value.first.return_value = rows[0] if rows else None
    db = SimpleNamespace(execute=AsyncMock(return_value=result), delete=AsyncMock(),
                         commit=AsyncMock(), rollback=AsyncMock())
    return db


class CleanupTests(unittest.IsolatedAsyncioTestCase):
    def test_retention_policy(self):
        for metadata in ({"razorpay_order_id": "order_1"},
                         {"razorpay_payment_id": "pay_1"},
                         {"payment_verified": True}, {"legacy_order_id": "order_2"}):
            self.assertTrue(preserve_temp_trip(metadata))
        for metadata in (None, {}, {"amount": 153}, {"razorpay_order_id": None}):
            self.assertFalse(preserve_temp_trip(metadata))

    async def test_scheduled_cleanup_preserves_expired_payment_linked_rows(self):
        protected = row({"razorpay_order_id": "order_1"})
        verified = row({"payment_verified": True})
        abandoned = row({})
        db = async_db([protected, verified, abandoned])
        cleanup = load_function("src/scheduler/tasks/cleanup_temp_trips.py", "a_cleanup_expired_temp_trips")
        self.assertEqual(await cleanup(db), 1)
        db.delete.assert_awaited_once_with(abandoned)

    async def test_customer_cleanup_preserves_order_after_failed_checkout(self):
        db = async_db([row({"razorpay_order_id": "order_1"})])
        cleanup = load_function("src/services/trips/booking_service.py", "a_delete_temp_trip_by_booking_id")
        self.assertFalse(await cleanup("booking", "customer", db))
        db.delete.assert_not_awaited()

    async def test_customer_cleanup_deletes_without_payment_order(self):
        abandoned = row({})
        db = async_db([abandoned])
        cleanup = load_function("src/services/trips/booking_service.py", "a_delete_temp_trip_by_booking_id")
        self.assertTrue(await cleanup("booking", "customer", db))
        db.delete.assert_awaited_once_with(abandoned)

    async def test_new_booking_cleanup_preserves_other_orders(self):
        abandoned = row({})
        db = async_db([row({"razorpay_order_id": "order_1"}), abandoned])
        cleanup = load_function("src/services/trips/trip_service.py", "a_delete_temp_trip")
        await cleanup("customer", db)
        db.delete.assert_awaited_once_with(abandoned)

    def test_sync_cleanup_preserves_other_orders(self):
        abandoned = row({})
        db = MagicMock()
        db.query.return_value.filter.return_value.with_for_update.return_value.all.return_value = [
            row({"razorpay_order_id": "order_1"}), abandoned]
        cleanup = load_function("src/services/trips/trip_service.py", "delete_temp_trip")
        cleanup("customer", db)
        db.delete.assert_called_once_with(abandoned)

    async def test_expiry_and_explicit_replacement_preserve_payment_order(self):
        existing = row({"razorpay_order_id": "order_1"})
        for replace in (False, True):
            db = async_db([existing])
            validate = load_function("src/services/validation_service.py", "a_validate_booking_request_hash",
                                     TripBookRequest=object, settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay"))
            result = await validate(SimpleNamespace(option=SimpleNamespace(hash="hash")), "customer", db,
                                    allow_removal_of_existing=replace)
            self.assertEqual(result, (existing, "order_1"))
            db.delete.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
