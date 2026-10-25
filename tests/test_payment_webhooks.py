import ast
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
from types import SimpleNamespace
from typing import Optional
import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException
from sqlalchemy import Column, Enum, DateTime, Index, Integer, String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base

from test_temp_trip_cleanup import ROOT, PaymentWebhookNotice, load_function
from test_booking_reconciliation_scheduler import Base as BookingBase, TemporaryBooking
from models.financial.payments_enum import ReconciliationStateEnum
from models.policies.refund_enum import PaymentProvider
from utils.retry import get_retry_delay_seconds

Base = declarative_base()
scope = dict(Base=Base, Column=Column, Enum=Enum, PaymentProvider=PaymentProvider, DateTime=DateTime, Index=Index, Integer=Integer,
             String=String, datetime=datetime, timezone=timezone)
tree = ast.parse((ROOT / "src/models/financial/payment_webhook_orm.py").read_text())
node = next(n for n in tree.body if isinstance(n, ast.ClassDef))
exec(compile(ast.Module(body=[node], type_ignores=[]), "payment_webhook_orm.py", "exec"), scope)
PaymentWebhookEvent = scope["PaymentWebhookEvent"]


class SignatureTests(unittest.TestCase):
    def setUp(self):
        self.settings = SimpleNamespace(RAZOR_PAY_WEBHOOK_SECRET="test_webhook_secret")
        self.parse = load_function(
            "src/services/razorpay_service.py", "parse_razorpay_webhook", Optional=Optional,
            PaymentWebhookNotice=PaymentWebhookNotice, settings=self.settings,
            HTTPException=HTTPException, hashlib=hashlib, hmac=hmac, json=json,
            EXPECTED_SIGNATURE_LENGTH=64, SERIES_CHARACTERS="0123456789abcdef", PaymentProvider=PaymentProvider)
        self.body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
            "id": "pay_1", "order_id": "order_1", "status": "captured"}}}}).encode()

    def signature(self, body):
        return hmac.new(b"test_webhook_secret", body, hashlib.sha256).hexdigest()

    def test_valid_raw_body(self):
        notice = self.parse(self.body, self.signature(self.body))
        self.assertEqual(notice.order_id, "order_1")
        self.assertEqual(notice.provider, "razorpay")

    def test_tampered_body_or_signature_is_rejected(self):
        for body, signature in ((self.body + b" ", self.signature(self.body)),
                                (self.body, ""), (self.body, "x" * 64), (self.body, "é" * 64)):
            with self.assertRaises(HTTPException) as error:
                self.parse(body, signature)
            self.assertEqual(error.exception.status_code, 401)

    def test_missing_secret_fails_closed(self):
        self.settings.RAZOR_PAY_WEBHOOK_SECRET = None
        with self.assertRaises(HTTPException) as error:
            self.parse(self.body, "")
        self.assertEqual(error.exception.status_code, 503)

    def test_signed_malformed_payload_is_rejected(self):
        for body in (b"{", b"[]", b'{"event":"payment.captured","payload":{}}'):
            with self.assertRaises(HTTPException) as error:
                self.parse(body, self.signature(body))
            self.assertEqual(error.exception.status_code, 400)

    def test_failure_event_is_ignored_without_reversing_capture(self):
        body = b'{"event":"payment.failed"}'
        self.assertIsNone(self.parse(body, self.signature(body)))


class InboxTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        BookingBase.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.db = SimpleNamespace(
            get=AsyncMock(side_effect=self.session.get), add=self.session.add,
            execute=AsyncMock(side_effect=self.session.execute),
            commit=AsyncMock(side_effect=self.session.commit), rollback=AsyncMock(side_effect=self.session.rollback))
        self.notice = PaymentWebhookNotice(provider="razorpay", event_type="payment.captured",
                                          order_id="order_1", payment_id="pay_1")
        self.reconcile = AsyncMock(return_value=SimpleNamespace(state=ReconciliationStateEnum.booked))

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def fn(self, name):
        fn = load_function("src/services/payment_webhook_service.py", name,
                           PaymentWebhookNotice=PaymentWebhookNotice,
                           PaymentWebhookEvent=PaymentWebhookEvent, HTTPException=HTTPException,
                           IntegrityError=IntegrityError, settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay"),
                           a_reconcile_booking=self.reconcile, AsyncSessionLocal=lambda: None, _EVENT_ID_MAX_LENGTH=255, _WEBHOOK_CLAIM_NEXT_ATTEMPT_AFTER_MINUTES=15, _DEFAULT_PAYMENT_WEBHOOK_BATCH_SIZE=20,
                           get_retry_delay_seconds=get_retry_delay_seconds)
        fn.__globals__.update(select=select, TempTrip=TemporaryBooking, Trip=TemporaryBooking)
        return fn

    async def store(self):
        await self.fn("a_store_payment_webhook")(self.notice, "event_1", "hash", self.db)

    def event(self):
        return self.session.get(PaymentWebhookEvent, {"provider": "razorpay", "event_id": "event_1"})

    async def test_duplicate_delivery_has_one_durable_record(self):
        await self.store()
        await self.store()
        self.assertEqual(len(self.session.execute(select(PaymentWebhookEvent)).scalars().all()), 1)

    async def test_conflicting_duplicate_is_rejected(self):
        await self.store()
        with self.assertRaises(HTTPException) as error:
            await self.fn("a_store_payment_webhook")(self.notice, "event_1", "different_hash", self.db)
        self.assertEqual(error.exception.status_code, 400)

    async def test_missing_event_id_is_rejected(self):
        with self.assertRaises(HTTPException):
            await self.fn("a_store_payment_webhook")(self.notice, "", "hash", self.db)

    async def test_claim_is_leased_and_recovers_after_expiry(self):
        await self.store()
        claim = self.fn("_claim_payment_webhooks")
        self.assertEqual(await claim(self.db), [("razorpay", "event_1", "order_1")])
        self.assertEqual(await claim(self.db), [])
        self.event().next_attempt_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        self.session.commit()
        self.assertEqual(len(await claim(self.db)), 1)

    async def process(self):
        @asynccontextmanager
        async def sessions():
            yield self.db
        fn = self.fn("a_process_payment_webhooks")
        fn.__globals__["_claim_payment_webhooks"] = self.fn("_claim_payment_webhooks")
        await fn(session_factory=sessions)

    async def test_capture_triggers_shared_reconciliation_and_marks_processed(self):
        await self.store()
        self.session.add(TemporaryBooking(id="booking_1", creator_id="customer",
                                         payment_provider_metadata={"razorpay_order_id": "order_1"}))
        self.session.commit()
        await self.process()
        self.reconcile.assert_awaited_once_with("booking_1", "customer", self.db, force_provider_check=True)
        self.assertIsNotNone(self.event().processed_at)
        await self.process()
        self.assertEqual(self.reconcile.await_count, 1)

    async def test_provider_outage_keeps_event_for_retry(self):
        await self.store()
        self.session.add(TemporaryBooking(id="booking_1", creator_id="customer",
                                         payment_provider_metadata={"razorpay_order_id": "order_1"}))
        self.session.commit()
        self.reconcile.side_effect = TimeoutError()
        await self.process()
        self.assertIsNone(self.event().processed_at)
        self.assertEqual(self.event().attempts, 1)

    async def test_unknown_order_is_retained_for_retry(self):
        await self.store()
        await self.process()
        self.assertIsNone(self.event().processed_at)
        self.reconcile.assert_not_awaited()

    async def test_webhook_counter_remains_accurate_while_delay_is_capped(self):
        await self.store()
        self.event().attempts = 16
        self.session.commit()
        before = datetime.now(timezone.utc)
        await self.process()  # Unknown association remains pending and is retried.
        event = self.event()
        self.assertEqual(event.attempts, 17)
        scheduled = event.next_attempt_at.replace(tzinfo=event.next_attempt_at.tzinfo or timezone.utc)
        self.assertAlmostEqual((scheduled - before).total_seconds(), 900, delta=2)


class WebhookRouteTests(unittest.IsolatedAsyncioTestCase):
    def route(self, receive):
        endpoint = load_function(
            "src/api/v1/endpoints/webhooks/razorpay.py", "razorpay_webhook",
            router=SimpleNamespace(post=lambda *args, **kwargs: lambda fn: fn),
            Request=object, BackgroundTasks=object, Header=lambda **kwargs: "",
            Depends=lambda dependency: None, a_yield_mysql_session=lambda: None,
            receive_payment_webhook=receive, a_process_payment_webhooks="processor")
        return endpoint

    async def test_raw_body_is_forwarded_and_work_scheduled_after_acceptance(self):
        receive = AsyncMock(return_value=True)
        request = SimpleNamespace(body=AsyncMock(return_value=b'{ "raw": true }'))
        tasks = MagicMock()
        result = await self.route(receive)(request, tasks, "signature", "event_1", "db")
        self.assertEqual(result, {"status": "accepted"})
        receive.assert_awaited_once_with("razorpay", b'{ "raw": true }', "signature", "event_1", "db")
        tasks.add_task.assert_called_once_with("processor", event_id="event_1", batch_size=1)

    async def test_storage_failure_is_not_acknowledged_or_scheduled(self):
        receive = AsyncMock(side_effect=RuntimeError("database unavailable"))
        tasks = MagicMock()
        with self.assertRaises(RuntimeError):
            await self.route(receive)(SimpleNamespace(body=AsyncMock(return_value=b"body")), tasks, "sig", "event", "db")
        tasks.add_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
