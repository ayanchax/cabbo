"""Provider and booking recovery regressions, without live credentials or network."""
import asyncio
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock

from test_temp_trip_cleanup import load_function, async_db, row, ReconciliationOutcome, RazorPayPaymentResponse
from models.financial.payments_enum import ReconciliationStateEnum


class BookingError(Exception):
    def __init__(self, message, **kwargs):
        super().__init__(message)
        self.status_code = kwargs.get("status_code")


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.client.order.fetch.return_value = {
            "id": "order_1", "amount": 15300, "currency": "INR", "status": "paid"}
        self.payment = {"id": "pay_1", "order_id": "order_1", "amount": 15300,
                        "currency": "INR", "status": "captured", "amount_refunded": 0}
        self.client.order.payments.return_value = {"items": [self.payment]}
        self.fetch = load_function(
            "src/services/razorpay_service.py", "fetch_razorpay_order_payment",
            razorpay=SimpleNamespace(Client=MagicMock(return_value=self.client)),
            settings=SimpleNamespace(RAZOR_PAY_KEY_ID="unused", RAZOR_PAY_KEY_SECRET="unused"))

    def test_captured_without_checkout_signature(self):
        self.assertEqual(self.fetch("order_1", 15300, "INR"), ReconciliationOutcome(state=ReconciliationStateEnum.captured, payment_id="pay_1"))
        self.client.order.fetch.assert_called_once_with("order_1", timeout=10)

    def test_order_amount_or_currency_mismatch_requires_review(self):
        for key, value in (("amount", 1), ("currency", "USD"), ("id", "wrong")):
            with self.subTest(key=key):
                original = self.client.order.fetch.return_value[key]
                self.client.order.fetch.return_value[key] = value
                self.assertEqual(self.fetch("order_1", 15300, "INR").state, "review_required")
                self.client.order.fetch.return_value[key] = original

    def test_payment_mismatch_or_refund_requires_review(self):
        for key, value in (("order_id", "wrong"), ("amount", 1), ("currency", "USD"), ("amount_refunded", 15300)):
            with self.subTest(key=key):
                original = self.payment[key]
                self.payment[key] = value
                self.assertEqual(self.fetch("order_1", 15300, "INR").state, "review_required")
                self.payment[key] = original

    def test_failed_or_authorized_attempt_is_not_terminal_failure(self):
        for state in ("failed", "authorized", "created"):
            self.payment["status"] = state
            self.assertEqual(self.fetch("order_1", 15300, "INR"), ReconciliationOutcome())

    def test_multiple_captures_require_review(self):
        self.client.order.payments.return_value = {"items": [self.payment, dict(self.payment, id="pay_2")]}
        self.assertEqual(self.fetch("order_1", 15300, "INR").state, "review_required")

    def test_failed_attempt_does_not_hide_a_captured_payment(self):
        self.client.order.payments.return_value = {
            "items": [dict(self.payment, id="pay_failed", status="failed"), self.payment]}
        self.assertEqual(self.fetch("order_1", 15300, "INR").state, "captured")


class ReconciliationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = row({"razorpay_order_id": "order_1"})
        self.temp.start_datetime = datetime.now(timezone.utc) + timedelta(hours=2)
        self.temp.platform_fee = 153
        self.db = async_db([self.temp])
        payment_info = RazorPayPaymentResponse(razorpay_order_id="order_1", razorpay_payment_id="pay_1", razorpay_signature=None)
        self.provider = MagicMock(return_value=ReconciliationOutcome(state=ReconciliationStateEnum.captured, payment_info=payment_info))
        self.existing = AsyncMock(return_value=None)
        self.finalise = AsyncMock(return_value=SimpleNamespace(trip_id="booking", booking_id="RENTAL-1", status="confirmed"))
        self.response = load_function("src/services/trips/reconciliation_service.py", "status_response", POLL_INTERVAL_SECONDS=10)

    def function(self):
        return load_function(
            "src/services/trips/reconciliation_service.py", "a_reconcile_booking",
            asyncio=asyncio, settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay"),
            a_existing_booking=self.existing, status_response=self.response,
            get_currency=lambda: SimpleNamespace(code="INR", lowest_unit_conversion_factor=100),
            convert_based_on_currency=lambda value, factor: value * factor,
            fetch_payment_order_status=self.provider,
            a_create_confirmed_trip_from_temp_trip=self.finalise, POLL_INTERVAL_SECONDS=10,
            TRIP_NOT_FOUND="not_found")

    async def test_recovers_without_callback_and_persists_evidence(self):
        result = await self.function()("booking", "customer", self.db)
        self.assertIs(result.state, ReconciliationStateEnum.booked)
        self.assertEqual(json.loads(result.model_dump_json())["state"], "booked")
        self.assertEqual(result.booking_id, "RENTAL-1")
        self.assertTrue(self.temp.payment_provider_metadata["payment_verified"])
        self.assertNotIn("razorpay_signature", self.temp.payment_provider_metadata)
        self.finalise.assert_awaited_once()

    async def test_uses_configured_provider_order_key(self):
        self.temp.payment_provider_metadata = {"another_provider_order_id": "order_other"}
        self.provider.return_value = ReconciliationOutcome()
        reconcile = self.function()
        reconcile.__globals__["settings"] = SimpleNamespace(PAYMENT_PROVIDER="another_provider")
        await reconcile("booking", "customer", self.db)
        self.provider.assert_called_once_with("order_other", 15300, "INR")

    async def test_records_configured_provider_provenance(self):
        await self.function()("booking", "customer", self.db)
        self.assertEqual(self.temp.payment_provider_metadata["payment_verified_via"], "razorpay_reconciliation")

    async def test_admin_actor_is_recorded_without_changing_booking_owner(self):
        await self.function()("booking", "customer", self.db, actor_id="admin_1")
        self.assertEqual(self.temp.payment_provider_metadata["reconciliation_requested_by"], "admin_1")
        self.finalise.assert_awaited_once()
        self.assertEqual(self.finalise.await_args.kwargs["requestor"], "admin_1")
        self.existing.assert_awaited_once_with("booking", "customer", self.db, "order_1")


    async def test_provider_outage_stays_checking_and_throttles(self):
        self.provider.side_effect = TimeoutError()
        reconcile = self.function()
        result = await reconcile("booking", "customer", self.db)
        self.assertEqual(result.state, "checking")
        self.assertFalse(result.can_retry_payment)
        await reconcile("booking", "customer", self.db)
        self.provider.assert_called_once()
        self.finalise.assert_not_awaited()

    async def test_pickup_passed_is_review_not_confirmed(self):
        self.temp.start_datetime = datetime.now(timezone.utc) - timedelta(minutes=1)
        result = await self.function()("booking", "customer", self.db)
        self.assertEqual(result.state, "review_required")
        self.assertTrue(self.temp.payment_provider_metadata["payment_verified"])
        self.finalise.assert_not_awaited()

    async def test_existing_cancelled_booking_is_not_reopened(self):
        self.existing.return_value = SimpleNamespace(id="existing", booking_id="RENTAL-1", status="cancelled")
        result = await self.function()("booking", "customer", self.db)
        self.assertEqual(result.trip_status, "cancelled")
        self.provider.assert_not_called()
        self.finalise.assert_not_awaited()

    async def test_confirmation_error_keeps_verified_booking_for_retry(self):
        self.finalise.side_effect = RuntimeError("database unavailable")
        result = await self.function()("booking", "customer", self.db)
        self.assertEqual(result.state, "checking")
        self.assertTrue(self.temp.payment_provider_metadata["payment_verified"])
        self.db.rollback.assert_awaited_once()

    async def test_review_result_is_durable_and_not_rechecked(self):
        self.provider.return_value = ReconciliationOutcome(state=ReconciliationStateEnum.review_required, reason="payment_mismatch_or_refund")
        reconcile = self.function()
        self.assertEqual((await reconcile("booking", "customer", self.db)).state, "review_required")
        await reconcile("booking", "customer", self.db)
        self.provider.assert_called_once()

    async def test_missing_or_other_customers_booking_is_not_reconciled(self):
        self.db = async_db([])
        # Inject the exception class into the isolated function's globals.
        reconcile = self.function()
        reconcile.__globals__["CabboException"] = BookingError
        with self.assertRaises(BookingError) as error:
            await reconcile("booking", "other_customer", self.db)
        self.assertEqual(error.exception.status_code, 404)
        self.provider.assert_not_called()
        self.finalise.assert_not_awaited()


class AdminReconciliationTests(unittest.IsolatedAsyncioTestCase):
    def endpoint(self, reconcile):
        endpoint = load_function(
            "src/api/v1/endpoints/admin/trip/recovery.py", "reconcile_booking",
            router=SimpleNamespace(post=lambda *args, **kwargs: lambda fn: fn),
            Depends=lambda dependency: None, User=object,
            a_yield_mysql_session=lambda: None, validate_user_token=lambda: None,
            RoleEnum=SimpleNamespace(super_admin="super_admin", customer_admin="customer_admin"),
            a_reconcile_booking_as_admin=reconcile)
        endpoint.__globals__["CabboException"] = BookingError
        return endpoint

    async def test_only_authorized_admin_roles_can_trigger_reconciliation(self):
        reconcile = AsyncMock(return_value="status")
        endpoint = self.endpoint(reconcile)
        for role in ("super_admin", "customer_admin"):
            self.assertEqual(await endpoint("booking", "db", SimpleNamespace(id="admin", role=role)), "status")
        self.assertEqual(reconcile.await_count, 2)
        for role in ("customer", "driver_admin", "driver"):
            with self.assertRaises(BookingError) as error:
                await endpoint("booking", "db", SimpleNamespace(id="unauthorized", role=role))
            self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(reconcile.await_count, 2)

    async def test_admin_service_resolves_owner_from_database(self):
        db = async_db(["customer_owner"])
        reconcile = AsyncMock(return_value="status")
        service = load_function(
            "src/services/trips/reconciliation_service.py", "a_reconcile_booking_as_admin",
            a_reconcile_booking=reconcile, TRIP_NOT_FOUND="not_found")
        self.assertEqual(await service("booking", "admin", db), "status")
        reconcile.assert_awaited_once_with("booking", "customer_owner", db, actor_id="admin")



class FinalisationTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeated_finalisation_returns_existing_booking(self):
        existing = SimpleNamespace(id="existing", booking_id="RENTAL-1", status="confirmed")
        temp = row({"razorpay_order_id": "order_1"})
        temp.creator_id = "customer"
        db = async_db([])  # Another worker has already consumed the temp row.
        response = AsyncMock(return_value="existing_response")
        finalise = load_function(
            "src/services/trips/booking_service.py", "a_create_confirmed_trip_from_temp_trip",
            RazorPayPaymentResponse=object, TripCreate=object,
            a_existing_booking=AsyncMock(return_value=existing),
            a_existing_booking_response=response, settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay"))
        self.assertEqual(await finalise(temp, "customer", None, db), "existing_response")
        db.delete.assert_not_awaited()
        response.assert_awaited_once_with(existing, db)

    async def test_finalisation_rechecks_pickup_after_lock(self):
        temp = row({"razorpay_order_id": "order_1", "payment_verified": True})
        temp.creator_id = "customer"
        temp.start_datetime = datetime.now(timezone.utc) - timedelta(seconds=1)
        db = async_db([temp])
        finalise = load_function(
            "src/services/trips/booking_service.py", "a_create_confirmed_trip_from_temp_trip",
            RazorPayPaymentResponse=object, TripCreate=object,
            a_existing_booking=AsyncMock(return_value=None), TRIP_NOT_FOUND="not_found",
            PAYMENT_VERIFIED_WITH_PENDING_CONFIRMATION="pending", settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay"))
        finalise.__globals__["CabboException"] = BookingError
        with self.assertRaises(BookingError):
            await finalise(temp, "customer", None, db)
        self.assertEqual(temp.payment_provider_metadata["reconciliation_state"], "review_required")
        db.commit.assert_awaited_once()
        db.delete.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
