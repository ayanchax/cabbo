"""Read-only status and durable reconciliation requests, using an isolated database."""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Response
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import Column, DateTime, JSON, String, create_engine, or_, and_, select
from sqlalchemy.orm import Session, declarative_base

from test_temp_trip_cleanup import load_function
from test_booking_reconciliation import BookingError
from models.financial.payments_enum import ReconciliationStateEnum

Base = declarative_base()


class Temp(Base):
    __tablename__ = "temp_trips"
    id = Column(String, primary_key=True)
    creator_id = Column(String)
    created_at = Column(DateTime, default=datetime.now)
    payment_provider_metadata = Column(JSON)


class Booked(Base):
    __tablename__ = "trips"
    id = Column(String, primary_key=True)
    creator_id = Column(String)
    booking_id = Column(String)
    status = Column(String)
    payment_provider_metadata = Column(JSON)
    payment_provider = Column(String)
    payment_order_id = Column(String)


class BookingStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.statements = []
        def execute(statement):
            self.statements.append(statement)
            return self.session.execute(statement)
        self.db = SimpleNamespace(execute=AsyncMock(side_effect=execute),
                                  commit=AsyncMock(side_effect=self.session.commit),
                                  rollback=AsyncMock(side_effect=self.session.rollback))
        self.temp = Temp(id="booking", creator_id="owner", payment_provider_metadata={"razorpay_order_id": "order_1"})
        self.session.add(self.temp)
        self.session.commit()
        self.response = load_function("src/services/trips/reconciliation_service.py", "_status_response", POLL_INTERVAL_SECONDS=10)

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def fn(self, name, path="src/services/trips/reconciliation_service.py"):
        fn = load_function(path, name, settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay"),
                           _status_response=self.response, POLL_INTERVAL_SECONDS=10,
                           TRIP_NOT_FOUND="not_found", AsyncSessionLocal=lambda: None)
        fn.__globals__.update(select=select, or_=or_, and_=and_, TempTrip=Temp, Trip=Booked,
                              CabboException=BookingError)
        return fn

    def requester(self):
        fn = self.fn("a_request_booking_reconciliation")
        fn.__globals__["a_existing_booking"] = self.fn("a_existing_booking", "src/services/trips/booking_service.py")
        return fn

    async def test_get_is_read_only_and_does_not_enqueue_or_lock(self):
        before = dict(self.temp.payment_provider_metadata)
        result = await self.fn("a_get_booking_payment_status")("booking", "owner", self.db)
        self.assertEqual(result.state, ReconciliationStateEnum.checking)
        self.assertEqual(self.temp.payment_provider_metadata, before)
        self.assertFalse(self.session.dirty)
        self.db.commit.assert_not_awaited()
        self.assertTrue(all(stmt._for_update_arg is None for stmt in self.statements))

    async def test_get_returns_confirmed_or_cancelled_booking_without_mutation(self):
        self.session.add(Booked(id="manual", creator_id="owner", booking_id="RENTAL-1", status="cancelled",
                                payment_provider="razorpay", payment_order_id="order_1",
                                payment_provider_metadata={"razorpay_order_id": "order_1"}))
        self.session.commit()
        result = await self.fn("a_get_booking_payment_status")("booking", "owner", self.db)
        self.assertEqual(result.trip_id, "manual")
        self.assertEqual(result.trip_status, "cancelled")
        self.db.commit.assert_not_awaited()

    async def test_post_persists_request_and_retries_do_not_duplicate_it(self):
        request = self.requester()
        await request("booking", "owner", self.db)
        self.session.refresh(self.temp)
        details = dict(self.temp.payment_provider_metadata)
        self.assertTrue(details["reconciliation_request_pending"])
        await request("booking", "owner", self.db)
        self.session.refresh(self.temp)
        self.assertEqual(self.temp.payment_provider_metadata, details)

    async def test_scheduler_recovers_post_when_background_never_runs(self):
        # A pending request should be eligible even when this order had an older backoff.
        self.temp.payment_provider_metadata = {"razorpay_order_id": "order_1",
            "reconciliation_next_check_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
        self.session.commit()
        await self.requester()("booking", "owner", self.db)
        self.session.close()
        self.session = Session(self.engine)  # New process/session sees the durable request.
        self.db.commit.side_effect = self.session.commit
        self.db.rollback.side_effect = self.session.rollback
        claim = load_function("src/scheduler/tasks/reconcile_bookings.py", "_claim_bookings",
                              _DEFAULT_BATCH_SIZE=20, _CLAIM_NEXT_ATTEMPT_AFTER_SECONDS=900,
                              settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay"), or_=or_)
        claim.__globals__.update(select=select, TempTrip=Temp)
        claimed = await claim(self.db)
        self.assertEqual(claimed, [("booking", "owner")])
        self.assertFalse(self.session.get(Temp, "booking").payment_provider_metadata["reconciliation_request_pending"])

    async def test_other_customer_cannot_read_or_queue_booking(self):
        for fn in (self.fn("a_get_booking_payment_status"), self.requester()):
            with self.assertRaises(BookingError) as error:
                await fn("booking", "someone_else", self.db)
            self.assertEqual(error.exception.status_code, 404)
        self.assertNotIn("reconciliation_request_pending", self.temp.payment_provider_metadata)

    async def test_review_state_is_not_requeued(self):
        self.temp.payment_provider_metadata = {"razorpay_order_id": "order_1", "reconciliation_state": "review_required"}
        self.session.commit()
        result = await self.requester()("booking", "owner", self.db)
        self.assertEqual(result.state, ReconciliationStateEnum.review_required)
        self.assertNotIn("reconciliation_request_pending", self.temp.payment_provider_metadata)

    async def test_background_failure_leaves_request_pending(self):
        await self.requester()("booking", "owner", self.db)
        @asynccontextmanager
        async def sessions():
            yield self.db
        process = self.fn("a_process_booking_reconciliation_request")
        process.__globals__["a_reconcile_booking"] = AsyncMock(side_effect=RuntimeError("interrupted"))
        await process("booking", "owner", session_factory=sessions)
        self.session.refresh(self.temp)
        self.assertTrue(self.temp.payment_provider_metadata["reconciliation_request_pending"])


class BookingStatusRouteTests(unittest.IsolatedAsyncioTestCase):
    def test_openapi_exposes_post_202_and_read_only_get(self):
        router = APIRouter()
        dependencies = dict(router=router, Response=Response, BackgroundTasks=BackgroundTasks,
                            Depends=Depends, Customer=object,
                            a_yield_mysql_session=lambda: None, validate_customer_token=lambda: None)
        load_function("src/api/v1/endpoints/customer/trip/payment.py", "booking_status",
                      a_get_booking_payment_status=AsyncMock(), **dependencies)
        load_function("src/api/v1/endpoints/customer/trip/payment.py", "request_booking_reconciliation",
                      a_request_booking_reconciliation=AsyncMock(),
                      a_process_booking_reconciliation_request=AsyncMock(), **dependencies)
        app = FastAPI()
        app.include_router(router, prefix="/api/v1/trips/bookings/payment")
        paths = app.openapi()["paths"]
        self.assertIn("202", paths["/api/v1/trips/bookings/payment/{temp_trip_id}/reconcile"]["post"]["responses"])
        self.assertIn("get", paths["/api/v1/trips/bookings/payment/status/{temp_trip_id}"])

    def fn(self, name, **dependencies):
        return load_function("src/api/v1/endpoints/customer/trip/payment.py", name,
                             router=SimpleNamespace(get=lambda *args, **kwargs: lambda fn: fn,
                                                    post=lambda *args, **kwargs: lambda fn: fn),
                             Response=object, BackgroundTasks=object, Customer=object,
                             Depends=lambda dep: None, a_yield_mysql_session=lambda: None,
                             validate_customer_token=lambda: None, **dependencies)

    async def test_get_calls_reader_only(self):
        reader = AsyncMock(return_value="stored_status")
        response = SimpleNamespace(headers={})
        fn = self.fn("booking_status", a_get_booking_payment_status=reader)
        self.assertEqual(await fn("booking", response, "db", SimpleNamespace(id="owner")), "stored_status")
        reader.assert_awaited_once_with("booking", "owner", "db")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_post_schedules_only_after_durable_queue_succeeds(self):
        queue = AsyncMock(return_value=SimpleNamespace(state=ReconciliationStateEnum.checking))
        tasks = MagicMock()
        fn = self.fn("request_booking_reconciliation", a_request_booking_reconciliation=queue,
                     a_process_booking_reconciliation_request="worker")
        await fn("booking", SimpleNamespace(headers={}), tasks, "db", SimpleNamespace(id="owner"))
        tasks.add_task.assert_called_once_with("worker", "booking", "owner")
        queue.side_effect = RuntimeError("commit failed")
        tasks.reset_mock()
        with self.assertRaises(RuntimeError):
            await fn("booking", SimpleNamespace(headers={}), tasks, "db", SimpleNamespace(id="owner"))
        tasks.add_task.assert_not_called()


if __name__ == "__main__":
    unittest.main()
