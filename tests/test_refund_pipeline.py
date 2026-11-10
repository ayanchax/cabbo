"""Refund provider recovery and real async ORM regressions; no live API calls."""
import ast
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
import importlib.util
import io
from pathlib import Path
import logging
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock
import uuid
from typing import Optional, Union, Any, Dict, List

from sqlalchemy import (Boolean, Column, DateTime, Enum as SAEnum, Float,
                        ForeignKey, Index, Integer, JSON, String, Text, and_, or_, select)
from sqlalchemy.orm import declarative_base, joinedload, relationship, sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.exc import MissingGreenlet
from sqlalchemy.dialects import mysql
from test_temp_trip_cleanup import ROOT, load_function as _load_function
from core import refund_error_codes as refund_errors
from models.financial.payments_enum import ReconciliationStateEnum
from models.policies.refund_enum import RefundStatus, RefundType, RefundTrigger, PaymentProvider
from models.trip.trip_enums import TripStatusEnum
from models.trip.trip_enums import CancellationSubStatusEnum, TripTypeEnum
from models.policies.refund_schema import RefundSchema
from apscheduler.triggers.interval import IntervalTrigger
from utils.retry import get_retry_delay_seconds


def load_function(*args, **kwargs):
    return _load_function(*args, refund_errors=refund_errors, **kwargs)


# Isolate provider functions from app settings and the configured real SDK client.
_provider_scope = dict(refund_errors=refund_errors, RefundStatus=RefundStatus,
                       ReconciliationStateEnum=ReconciliationStateEnum)
_provider_tree = ast.parse((ROOT / "src/services/razorpay_refund_service.py").read_text())
_provider_nodes = [n for n in _provider_tree.body if isinstance(
    n, (ast.ClassDef, ast.FunctionDef, ast.Assign))]
exec(compile(ast.Module(body=_provider_nodes, type_ignores=[]), "razorpay_refund_service.py", "exec"), _provider_scope)
RefundReviewRequired = _provider_scope["RefundReviewRequired"]
RefundRetryableError = _provider_scope["RefundRetryableError"]
reconcile_or_submit_refund = _provider_scope["reconcile_or_submit_refund"]
fetch_refund = _provider_scope["fetch_refund"]


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        _provider_scope["create_razorpay_refund_client"] = lambda: self.client
        self.client.payment.fetch.return_value = {
            "id": "pay_1", "order_id": "order_1", "amount": 15000,
            "currency": "INR", "status": "captured", "amount_refunded": 0,
            # No settlement_id: capture, not merchant settlement, matters.
        }
        self.response = {"id": "rfnd_1", "payment_id": "pay_1", "amount": 15000,
                         "currency": "INR", "status": "pending"}
        self.client.payment.refund.return_value = self.response
        self.client.payment.fetch_multiple_refund.return_value = {"items": []}
        self.args = dict(payment_id="pay_1", amount=15000, original_amount=15000,
                         currency="INR", order_id="order_1", idempotency_key="stable-key", entity_id="trip_1")

    def run_refund(self):
        return reconcile_or_submit_refund(**self.args)

    def test_captured_unsettled_payment_is_submitted_idempotently(self):
        self.assertEqual(self.run_refund(), self.response)
        args, kwargs = self.client.payment.refund.call_args
        self.assertEqual(args[1]["amount"], 15000)
        self.assertEqual(kwargs["headers"], {"X-Refund-Idempotency": "stable-key"})

    def test_existing_manual_refund_is_adopted_without_submitting(self):
        self.client.payment.fetch_multiple_refund.return_value = {"items": [self.response]}
        self.assertEqual(self.run_refund(), self.response)
        self.client.payment.refund.assert_not_called()

    def test_manual_full_refund_after_payment_status_refunded_is_adopted(self):
        self.client.payment.fetch.return_value.update(status="refunded", amount_refunded=15000)
        self.test_existing_manual_refund_is_adopted_without_submitting()

    def test_amount_identity_failed_and_multiple_refunds_require_review(self):
        for changes in ({"amount": 100}, {"payment_id": "other"}, {"currency": "USD"}):
            self.client.payment.fetch_multiple_refund.return_value = {"items": [dict(self.response, **changes)]}
            with self.assertRaises(RefundReviewRequired):
                self.run_refund()
        self.client.payment.fetch_multiple_refund.return_value = {"items": [self.response, self.response]}
        with self.assertRaises(RefundReviewRequired):
            self.run_refund()
        self.client.payment.refund.assert_not_called()

    def test_failed_refund_is_returned_as_failed_without_new_submission(self):
        failed = dict(self.response, status="failed")
        self.client.payment.fetch_multiple_refund.return_value = {"items": [failed]}
        self.assertEqual(self.run_refund(), failed)
        self.client.payment.refund.assert_not_called()

    def test_payment_mismatch_never_submits(self):
        self.client.payment.fetch.return_value["order_id"] = "other"
        with self.assertRaises(RefundReviewRequired):
            self.run_refund()
        self.client.payment.refund.assert_not_called()

    def test_invalid_refund_amount_never_submits(self):
        for amount in (0, -1, 50, 15001):
            self.args["amount"] = amount
            with self.assertRaises(RefundReviewRequired):
                self.run_refund()
        self.client.payment.refund.assert_not_called()

    def test_insufficient_balance_is_retryable(self):
        self.client.payment.refund.side_effect = RuntimeError("not enough balance")
        with self.assertRaisesRegex(RefundRetryableError, "insufficient_provider_balance"):
            self.run_refund()

    def test_lost_response_is_recovered_without_second_submission(self):
        self.client.payment.refund.side_effect = TimeoutError()
        with self.assertRaises(RefundRetryableError):
            self.run_refund()
        self.client.payment.fetch_multiple_refund.return_value = {"items": [self.response]}
        self.assertEqual(self.run_refund(), self.response)
        self.client.payment.refund.assert_called_once()

    def test_authorized_payment_is_retryable_without_submission(self):
        self.client.payment.fetch.return_value["status"] = "authorized"
        with self.assertRaisesRegex(RefundRetryableError, "payment_not_captured_yet"):
            self.run_refund()
        self.client.payment.refund.assert_not_called()

    def test_polling_unknown_state_is_not_failed(self):
        self.client.refund.fetch.return_value = dict(self.response, status="unknown")
        with self.assertRaises(RefundRetryableError):
            fetch_refund(refund_id="rfnd_1", payment_id="pay_1", amount=15000, currency="INR")

    def test_installed_sdk_passes_idempotency_header_and_integer_amount(self):
        import json
        import razorpay
        client = razorpay.Client(auth=("test_id", "test_secret"))
        def response(body):
            result = MagicMock()
            result.status_code = 200
            result.json.return_value = body
            return result
        client.session.request = MagicMock(side_effect=[
            response(self.client.payment.fetch.return_value), response({"items": []}), response(self.response)])
        _provider_scope["create_razorpay_refund_client"] = lambda: client
        reconcile_or_submit_refund(**self.args)
        request = client.session.request.call_args
        self.assertEqual(request.kwargs["headers"]["X-Refund-Idempotency"], "stable-key")
        self.assertEqual(json.loads(request.kwargs["data"])["amount"], 15000)


Base = declarative_base()


class Customer(Base):
    __tablename__ = "customers"
    id = Column(String, primary_key=True)
    name = Column(String)
    email = Column(String)


class Trip(Base):
    __tablename__ = "trips"
    id = Column(String, primary_key=True)
    creator_id = Column(String, ForeignKey("customers.id"))
    status = Column(String)
    advance_payment = Column(Float)
    booking_id = Column(String)
    is_active = Column(Boolean, default=True)
    payment_provider_metadata = Column(JSON)
    customer = relationship(Customer, lazy="raise")
    refund = relationship("Refund", back_populates="trip", uselist=False)


class Cancellation(Base):
    __tablename__ = "cancellations"
    id = Column(String, primary_key=True)


class Audit(Base):
    __tablename__ = "audits"
    id = Column(String, primary_key=True)


# Exercise the actual refund columns/relationships without importing app settings.
scope = dict(Base=Base, Column=Column, DateTime=DateTime, JSON=JSON, String=String,
             MySQL_CHAR=String, Integer=Integer, Float=Float, Boolean=Boolean, Text=Text,
             Index=Index, ForeignKey=ForeignKey, SAEnum=SAEnum, relationship=relationship,
             RefundStatus=RefundStatus, RefundType=RefundType, RefundTrigger=RefundTrigger,
             PaymentProvider=PaymentProvider, datetime=datetime, timezone=timezone, uuid=uuid)
node = next(n for n in ast.parse((ROOT / "src/models/policies/refund_orm.py").read_text()).body
            if isinstance(n, ast.ClassDef) and n.name == "Refund")
exec(compile(ast.Module(body=[node], type_ignores=[]), "refund_orm.py", "exec"), scope)
Refund = scope["Refund"]


def worker_scope():
    config = SimpleNamespace(currency="INR", currency_lowest_unit_conversion_factor=100,
                             currency_decimal_places=2, currency_symbol="INR")
    ns = dict(refund_errors=refund_errors, asyncio=asyncio, datetime=datetime, timedelta=timedelta, timezone=timezone,
              Decimal=Decimal, ROUND_HALF_UP=ROUND_HALF_UP, NAMESPACE_URL=uuid.NAMESPACE_URL,
              uuid5=uuid.uuid5, select=select, or_=or_, and_=and_, joinedload=joinedload,
              RefundORM=Refund, Trip=Trip, RefundStatus=RefundStatus, TripStatusEnum=TripStatusEnum,
              AsyncSession=AsyncSession, REFUND_POLL_BATCH_SIZE=50, REFUND_LEASE_MINUTES=15,
              get_retry_delay_seconds=get_retry_delay_seconds, log=logging.getLogger(__name__),
              RefundReviewRequired=RefundReviewRequired, RefundRetryableError=RefundRetryableError,
              get_payment_id_prefix=lambda **kwargs: "pay_",
              get_refund_id_prefix=lambda **kwargs: "rfnd_",
              task=lambda **kwargs: lambda fn: fn,
              settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay", get_config_store=lambda:
                  SimpleNamespace(geographies=SimpleNamespace(country_server=config))),
              notify_trip_cancellation_to_customer=AsyncMock(return_value=True),
              send_refund_credited_notification=AsyncMock(return_value=True))
    tree = ast.parse((ROOT / "src/scheduler/tasks/process_refund.py").read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "process_refund.py", "exec"), ns)
    lookup = load_function("src/services/refund_service.py", "get_refund_for_processing",
                           Optional=Optional, RefundORM=Refund, joinedload=joinedload)
    lookup.__globals__.update(select=select, Trip=Trip)
    ns["get_refund_for_processing"] = lookup
    ns.update(reconcile_or_submit_refund=MagicMock(return_value={
                  "id": "rfnd_1", "payment_id": "pay_1", "amount": 15000,
                  "currency": "INR", "status": "pending"}),
              fetch_refund=MagicMock(return_value={
                  "id": "rfnd_1", "payment_id": "pay_1", "amount": 15000,
                  "currency": "INR", "status": "processed"}))
    return ns


class PaymentDispatchTests(unittest.TestCase):
    def function(self, name):
        self.client = object()
        self.factory = MagicMock(return_value=self.client)
        self.submit = MagicMock(return_value={"id": "rfnd_1"})
        self.fetch = MagicMock(return_value={"id": "rfnd_1", "status": "processed"})
        return load_function("src/services/payment_service.py", name,
            PAYMENT_PROVIDER="razorpay", PaymentProvider=PaymentProvider,
            RefundReviewRequired=RefundReviewRequired,
            create_razorpay_refund_client=self.factory,
            reconcile_or_submit_razorpay_refund=self.submit, fetch_razorpay_refund=self.fetch)

    def test_submission_routes_through_payment_service(self):
        submit = self.function("reconcile_or_submit_refund")
        args = dict(payment_id="pay_1", amount=15000, original_amount=15000,
                    currency="INR", order_id="order_1", idempotency_key="stable", entity_id="trip_1")
        self.assertEqual(submit(**args), {"id": "rfnd_1"})
        self.submit.assert_called_once_with(**args)

    def test_polling_routes_through_payment_service_and_preserves_errors(self):
        fetch = self.function("fetch_refund")
        args = dict(refund_id="rfnd_1", payment_id="pay_1", amount=15000, currency="INR")
        self.assertEqual(fetch(**args)["status"], "processed")
        self.fetch.assert_called_once_with(**args)
        self.fetch.side_effect = RefundRetryableError("unavailable")
        with self.assertRaises(RefundRetryableError):
            fetch(**args)

    def test_unsupported_provider_never_constructs_razorpay_client(self):
        fetch = self.function("fetch_refund")
        with self.assertRaises(RefundReviewRequired):
            fetch(refund_id="other", payment_id="other", amount=100, currency="INR", provider="stripe")
        self.factory.assert_not_called()
        self.fetch.assert_not_called()


@unittest.skipUnless(importlib.util.find_spec("aiosqlite"), "install aiosqlite for async ORM regressions")
class AsyncRefundTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.sessions = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        self.ns = worker_scope()
        async with self.sessions() as db:
            db.add(Customer(id="customer", name="Founder", email="test@example.com"))
            await db.commit()
        await self.add()

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def add(self, identifier="intent", **changes):
        async with self.sessions() as db:
            trip = Trip(id=identifier, creator_id="customer", status="cancelled", advance_payment=150,
                        booking_id=identifier, payment_provider_metadata={
                            "razorpay_payment_id": "pay_1", "razorpay_order_id": "order_1"})
            db.add(trip)
            await db.flush()
            values = dict(id=identifier, entity_id=identifier, refund_amount=150,
                          refund_description="Cancellation", refund_status=RefundStatus.initiated,
                          refund_provider=PaymentProvider.razorpay, refund_details={"id": "pay_1"})
            values.update(changes)
            db.add(Refund(**values))
            await db.commit()

    async def read(self, identifier="intent"):
        async with self.sessions() as db:
            return await db.get(Refund, identifier)

    async def due(self, identifier="intent"):
        async with self.sessions() as db:
            row = await db.get(Refund, identifier)
            row.next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            await db.commit()

    async def run_worker(self):
        await self.ns["_run_refund_status_sync"](self.sessions)

    async def test_submission_then_poll_then_no_more_work(self):
        await self.run_worker()
        row = await self.read()
        self.assertEqual(row.id, "intent")  # Never mutate the local primary key.
        self.assertEqual(row.provider_refund_id, "rfnd_1")
        self.assertEqual(row.refund_status, RefundStatus.pending)
        self.assertIsNotNone(row.cancellation_notified_at)
        await self.due()
        await self.run_worker()
        row = await self.read()
        self.assertEqual(row.refund_status, RefundStatus.processed)
        self.assertIsNotNone(row.processed_notified_at)
        await self.due()
        await self.run_worker()
        self.ns["reconcile_or_submit_refund"].assert_called_once()
        self.ns["fetch_refund"].assert_called_once()
        self.ns["send_refund_credited_notification"].assert_awaited_once()

    async def test_claim_lease_and_expiry(self):
        async with self.sessions() as db:
            self.assertEqual(await self.ns["_fetch_actionable_refunds"](db), ["intent"])
        async with self.sessions() as db:
            self.assertEqual(await self.ns["_fetch_actionable_refunds"](db), [])
        await self.due()
        async with self.sessions() as db:
            self.assertEqual(await self.ns["_fetch_actionable_refunds"](db), ["intent"])
        self.assertEqual((await self.read()).attempts, 2)

    async def test_claim_excludes_complete_inactive_and_not_due_rows(self):
        now = datetime.now(timezone.utc)
        await self.add("complete", refund_status=RefundStatus.processed,
                       processed_notified_at=now, cancellation_notified_at=now)
        await self.add("inactive", is_active=False)
        await self.add("later", next_attempt_at=now + timedelta(hours=1))
        async with self.sessions() as db:
            self.assertEqual(await self.ns["_fetch_actionable_refunds"](db), ["intent"])

    async def test_unrecoverable_id_is_reviewed_instead_of_deactivated(self):
        async with self.sessions() as db:
            row = await db.get(Refund, "intent")
            row.refund_details = {}
            trip = await db.get(Trip, "intent")
            trip.payment_provider_metadata = {}
            await db.commit()
        await self.run_worker()
        row = await self.read()
        self.assertTrue(row.review_required)
        self.assertTrue(row.is_active)
        self.assertEqual(row.last_error, "missing_payment_id")
        self.ns["reconcile_or_submit_refund"].assert_not_called()

    async def test_balance_failure_preserves_obligation_and_retry_identity(self):
        self.ns["reconcile_or_submit_refund"].side_effect = RefundRetryableError("insufficient_provider_balance")
        await self.run_worker()
        row = await self.read()
        self.assertTrue(row.is_active)
        self.assertFalse(row.review_required)
        self.assertEqual(row.last_error, "insufficient_provider_balance")
        key = row.idempotency_key
        await self.due()
        await self.run_worker()
        self.assertEqual((await self.read()).idempotency_key, key)

    async def test_missing_id_is_recovered_from_trip(self):
        async with self.sessions() as db:
            row = await db.get(Refund, "intent")
            row.refund_details = {}
            await db.commit()
        await self.run_worker()
        self.assertEqual((await self.read()).payment_id, "pay_1")

    def intent_function(self):
        add = load_function("src/services/refund_service.py", "_add_refund_details_for_trip",
            RefundSchema=RefundSchema, RefundORM=Refund, uuid5=uuid.uuid5, NAMESPACE_URL=uuid.NAMESPACE_URL)
        config = self.ns["settings"].get_config_store()
        review = load_function("src/services/refund_service.py", "_record_refund_review",
            RefundSchema=RefundSchema, RefundType=RefundType, RefundStatus=RefundStatus,
            PaymentProvider=PaymentProvider, settings=self.ns["settings"], uuid4=uuid.uuid4,
            _add_refund_details_for_trip=add)
        return load_function("src/services/refund_service.py", "refund_advance_payment_to_customer_on_cancellation",
            TripDetailSchema=object, ConfigStore=object, CancellationSubStatusEnum=CancellationSubStatusEnum,
            settings=self.ns["settings"], Optional=Optional, RefundSchema=RefundSchema,
            CancelationPolicySchema=object, TripTypeEnum=TripTypeEnum, RefundType=RefundType,
            RefundStatus=RefundStatus, PaymentProvider=PaymentProvider, Currency=SimpleNamespace,
            PaymentNotesSchema=SimpleNamespace, CustomerPayment=SimpleNamespace,
            _is_existing_refund=AsyncMock(return_value=False), _add_refund_details_for_trip=add,
            _record_refund_review=review,
            get_cancelation_policy_id=lambda policy: None, uuid4=uuid.uuid4,
            get_initial_refund_response=lambda **kw: {"id": kw["payment_id"],
                "payment_id": kw["payment_id"], "notes": {}, "currency": kw["currency"].code})

    async def test_missing_policy_is_retained_without_promising_or_submitting_money(self):
        await self.prepare_cancellation()
        queue = self.intent_function()
        # No regional policy is configured. This must become visible review work,
        # not an automatic zero-entitlement decision or an assumed full refund.
        trip = SimpleNamespace(id="cancel", advance_payment=150,
            trip_type_master=SimpleNamespace(trip_type=TripTypeEnum.local, id="local"),
            origin=SimpleNamespace(region_code="region"))
        async with self.sessions() as db:
            await queue(trip, db, CancellationSubStatusEnum.customer_cancelled,
                        requestor="customer", commit=False)
            await db.commit()
        async with self.sessions() as db:
            row = (await db.execute(select(Refund).where(Refund.entity_id == "cancel"))).scalars().one()
            self.assertTrue(row.review_required)
            self.assertEqual(row.refund_amount, 0)
            self.assertEqual(row.last_error, "missing_cancellation_policy")
        await self.run_worker()
        # Only the original "intent" fixture may be submitted, not "cancel".
        self.assertTrue(all(call.kwargs["entity_id"] != "cancel"
                            for call in self.ns["reconcile_or_submit_refund"].call_args_list))

    async def cancellation_function(self, fail_after_intent=False):
        async def attach(trip, db, **kwargs):
            await db.refresh(trip, attribute_names=["customer"])
        async def register(payload, db, **kwargs):
            row = Cancellation(id=payload.entity_id)
            db.add(row)
            await db.flush()
            return row
        async def audit(trip_id, db, **kwargs):
            db.add(Audit(id=trip_id))
        queue = self.intent_function()
        async def persist(*args, **kwargs):
            await queue(*args, **kwargs)
            if fail_after_intent:
                raise RuntimeError("simulated failure before atomic commit")
        return load_function("src/services/trips/status_service.py", "_cancelled",
            Union=Union, User=object, Customer=Customer, Optional=Optional,
            CancelationSchema=SimpleNamespace,
            TripStatusEnum=TripStatusEnum, AdditionalDetailsOnTripStatusChange=object,
            TripResponseView=SimpleNamespace(ADMIN_DETAIL="admin"),
            TripDetailSchema=SimpleNamespace(model_validate=lambda trip: SimpleNamespace(
                id=trip.id, advance_payment=trip.advance_payment, customer=trip.customer,
                payment_provider_metadata=trip.payment_provider_metadata)),
            get_cancellation_by_trip_id=AsyncMock(return_value=None),
            get_cancelation_sub_status=lambda **kwargs: CancellationSubStatusEnum.other,
            get_cancelation_payload=lambda **kwargs: SimpleNamespace(entity_id=kwargs["trip_id"], reason="cancel"),
            register_trip_cancellation=register, a_log_trip_audit=audit,
            attach_relationships_to_trip=attach,
            refund_advance_payment_to_customer_on_cancellation=persist)

    async def prepare_cancellation(self):
        await self.add("cancel")
        async with self.sessions() as db:
            refund = await db.get(Refund, "cancel")
            await db.delete(refund)
            trip = await db.get(Trip, "cancel")
            trip.status = "confirmed"
            await db.commit()

    async def test_cancellation_and_intent_commit_together(self):
        await self.prepare_cancellation()
        cancel = await self.cancellation_function()
        async with self.sessions() as db:
            trip = await db.get(Trip, "cancel")
            trip.driver_id = None
            _, background = await cancel(trip, db, TripStatusEnum.cancelled,
                SimpleNamespace(id="admin"), SimpleNamespace(reason="cancel", cancelation_detail=None))
            self.assertIsNone(background)
        async with self.sessions() as db:
            self.assertEqual((await db.get(Trip, "cancel")).status, "cancelled")
            self.assertIsNotNone(await db.get(Cancellation, "cancel"))
            self.assertIsNotNone(await db.get(Audit, "cancel"))
            self.assertIsNotNone((await db.execute(select(Refund).where(Refund.entity_id == "cancel"))).scalars().one())
        self.ns["reconcile_or_submit_refund"].assert_not_called()

    async def test_failed_cancellation_transaction_keeps_neither_intent_nor_cancel(self):
        await self.prepare_cancellation()
        cancel = await self.cancellation_function(fail_after_intent=True)
        async with self.sessions() as db:
            trip = await db.get(Trip, "cancel")
            trip.driver_id = None
            with self.assertRaises(RuntimeError):
                await cancel(trip, db, TripStatusEnum.cancelled,
                    SimpleNamespace(id="admin"), SimpleNamespace(reason="cancel", cancelation_detail=None))
            await db.rollback()
        async with self.sessions() as db:
            self.assertEqual((await db.get(Trip, "cancel")).status, "confirmed")
            self.assertIsNone(await db.get(Cancellation, "cancel"))
            self.assertIsNone(await db.get(Audit, "cancel"))
            self.assertIsNone((await db.execute(select(Refund).where(Refund.entity_id == "cancel"))).scalars().first())

    async def test_intent_is_rolled_back_with_cancellation_and_never_calls_provider(self):
        await self.add("new")
        async with self.sessions() as db:
            existing = await db.get(Refund, "new")
            await db.delete(existing)
            await db.commit()
        trip_schema = SimpleNamespace(id="new", advance_payment=150,
            payment_provider_metadata={"razorpay_payment_id": "pay_1"},
            customer=SimpleNamespace(id="customer", name="Founder"))
        queue = self.intent_function()
        async with self.sessions() as db:
            trip = await db.get(Trip, "new")
            trip.status = "cancelled"
            self.assertTrue(await queue(trip_schema, db, CancellationSubStatusEnum.other,
                                        requestor="admin", commit=False))
            result = await db.execute(select(Refund).where(Refund.entity_id == "new"))
            intent = result.scalars().one()
            self.assertNotEqual(intent.id, "pay_1")
            self.assertTrue(intent.idempotency_key)
            await db.rollback()
        async with self.sessions() as db:
            result = await db.execute(select(Refund).where(Refund.entity_id == "new"))
            self.assertIsNone(result.scalars().first())
        self.ns["reconcile_or_submit_refund"].assert_not_called()

    async def test_admin_requeue_preserves_provider_identity(self):
        async with self.sessions() as db:
            row = await db.get(Refund, "intent")
            row.review_required = True
            row.provider_refund_id = "rfnd_1"
            row.idempotency_key = "original-key"
            await db.commit()
        queue = load_function("src/services/refund_service.py", "queue_refund_retry",
                              RefundORM=Refund, TRIP_NOT_FOUND="missing")
        queue.__globals__["select"] = select
        async with self.sessions() as db:
            await queue("intent", db, "admin")
        row = await self.read()
        self.assertFalse(row.review_required)
        self.assertEqual((row.provider_refund_id, row.idempotency_key), ("rfnd_1", "original-key"))
        self.assertEqual(row.refund_details["retry_requested_by"], "admin")

    async def test_admin_creation_uses_original_customer_cancellation_reason(self):
        queue = AsyncMock(return_value=True)
        review = AsyncMock(return_value=True)
        schema = SimpleNamespace(cancellation=SimpleNamespace(
            cancellation_sub_status=CancellationSubStatusEnum.customer_cancelled))
        create = load_function("src/services/refund_service.py", "initiate_refund_by_booking_id",
            CancellationSubStatusEnum=CancellationSubStatusEnum,
            TripStatusEnum=TripStatusEnum, TripResponseView=SimpleNamespace(ADMIN_DETAIL="admin"),
            TripDetailSchema=SimpleNamespace(model_validate=lambda trip: schema),
            attach_relationships_to_trip=AsyncMock(),
            refund_advance_payment_to_customer_on_cancellation=queue, _record_refund_review=review,
            TRIP_NOT_FOUND="missing")
        create.__globals__.update(Trip=Trip, select=select)
        async with self.sessions() as db:
            await create("intent", "admin", db)
        self.assertEqual(queue.call_args.kwargs["cancelation_sub_status"],
                         CancellationSubStatusEnum.customer_cancelled)
        review.assert_not_awaited()
        schema.cancellation = None
        async with self.sessions() as db:
            await create("intent", "admin", db)
        self.assertEqual(review.call_args.args[2], "missing_cancellation_reason")
        queue.assert_awaited_once()

    async def test_mismatch_is_retained_for_review_and_not_reclaimed(self):
        self.ns["reconcile_or_submit_refund"].side_effect = RefundReviewRequired("provider_refund_mismatch")
        await self.run_worker()
        self.assertTrue((await self.read()).review_required)
        await self.due()
        await self.run_worker()
        self.ns["reconcile_or_submit_refund"].assert_called_once()

    async def test_email_failure_retries_email_without_money_operation(self):
        self.ns["reconcile_or_submit_refund"].return_value["status"] = "processed"
        self.ns["send_refund_credited_notification"].return_value = False
        await self.run_worker()
        row = await self.read()
        self.assertEqual(row.refund_status, RefundStatus.processed)
        self.assertIsNone(row.processed_notified_at)
        self.ns["send_refund_credited_notification"].return_value = True
        await self.due()
        await self.run_worker()
        self.ns["reconcile_or_submit_refund"].assert_called_once()
        self.ns["fetch_refund"].assert_not_called()
        self.assertIsNotNone((await self.read()).processed_notified_at)

    async def test_failed_provider_transition_is_persisted_for_review(self):
        await self.run_worker()
        await self.due()
        self.ns["fetch_refund"].return_value["status"] = "failed"
        await self.run_worker()
        row = await self.read()
        self.assertEqual(row.refund_status, RefundStatus.failed)
        self.assertTrue(row.review_required)
        self.assertEqual(row.last_error, "provider_refund_failed")
        await self.due()
        await self.run_worker()
        self.ns["fetch_refund"].assert_called_once()

    async def test_rollback_expiration_reproduces_greenlet_and_worker_isolates_items(self):
        # expire_on_commit=False does not protect against rollback expiration.
        async with self.sessions() as db:
            refund = await db.get(Refund, "intent")
            await db.rollback()
            with self.assertRaises(MissingGreenlet):
                _ = refund.entity_id
        await self.add("second")
        original = self.ns["process_single_refund"]
        async def process(db, refund):
            if refund.id == "intent":
                await db.rollback()
                raise RuntimeError("simulated failed transaction")
            await original(db, refund)
        self.ns["process_single_refund"] = process
        await self.run_worker()
        self.assertEqual((await self.read("second")).refund_status, RefundStatus.pending)


class MigrationTests(unittest.TestCase):
    def test_refund_schedule_uses_configured_minutes(self):
        tree = ast.parse((ROOT / "src/scheduler/tasks/__init__.py").read_text())
        ns = dict(Any=Any, Dict=Dict, List=List, IntervalTrigger=IntervalTrigger,
                  settings=SimpleNamespace(REFUND_POLL_INTERVAL_MINUTES=3,
                    RECONCILE_BOOKING_INTERVAL_MINUTES=1, RECONCILE_BATCH_SIZE=20),
                  sync_pending_refund_statuses_task=object(), cleanup_temp_trips_task=object(),
                  reconcile_bookings_task=object())
        nodes = [n for n in tree.body if isinstance(n, (ast.Assign, ast.AnnAssign))]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), "tasks.py", "exec"), ns)
        job = next(t for t in ns["TASKS"] if t["id"].endswith("sync_pending_refund_statuses"))
        self.assertEqual(job["trigger"].interval.total_seconds(), 180)
        self.assertEqual(job["max_instances"], 1)

    def test_single_revision_head_and_mysql_upgrade(self):
        import runpy
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        revisions, parents = set(), set()
        for path in (ROOT / "alembic/versions").glob("*.py"):
            values = {}
            for node in ast.parse(path.read_text()).body:
                if isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for target in targets:
                        if getattr(target, "id", "") in ("revision", "down_revision"):
                            values[target.id] = ast.literal_eval(node.value)
            if "revision" in values:
                revisions.add(values["revision"])
                parent = values.get("down_revision")
                parents.update(parent if isinstance(parent, tuple) else [parent])
        self.assertEqual(revisions - parents, {"d7e8f9a0b1c2"})
        output = io.StringIO()
        context = MigrationContext.configure(dialect=mysql.dialect(), opts={"as_sql": True, "output_buffer": output})
        module = runpy.run_path(str(ROOT / "alembic/versions/d7e8f9a0b1c2_durable_refund_processing.py"))
        module["upgrade"].__globals__["op"] = Operations(context)
        module["upgrade"]()
        self.assertIn("ix_refunds_due", output.getvalue())
        self.assertIn("uq_refunds_idempotency_key", output.getvalue())
        module["downgrade"].__globals__["op"] = Operations(context)
        module["downgrade"]()
        self.assertIn("DROP COLUMN processed_notified_at", output.getvalue())


if __name__ == "__main__":
    unittest.main()
