"""Exercise scheduler selection and retry persistence using an isolated SQLite DB."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import Column, DateTime, JSON, String, create_engine, or_
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.dialects import mysql

from test_temp_trip_cleanup import load_function
from models.financial.payments_enum import ReconciliationStateEnum

Base = declarative_base()


class TemporaryBooking(Base):
    __tablename__ = "temp_trips"
    id = Column(String, primary_key=True)
    creator_id = Column(String)
    created_at = Column(DateTime)
    payment_provider_metadata = Column(JSON)


class SchedulerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.statements = []

        def execute(statement):
            self.statements.append(statement)
            return self.session.execute(statement)

        self.db = SimpleNamespace(execute=AsyncMock(side_effect=execute),
                                  commit=AsyncMock(side_effect=self.session.commit))

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def add(self, identifier, metadata, age=1):
        booking = TemporaryBooking(id=identifier, creator_id="customer",
                                   created_at=datetime.now(timezone.utc) - timedelta(hours=age),
                                   payment_provider_metadata=metadata)
        self.session.add(booking)
        self.session.commit()
        return booking

    def function(self, name):
        fn = load_function("src/scheduler/tasks/reconcile_bookings.py", name,
                           settings=SimpleNamespace(PAYMENT_PROVIDER="configured_provider"),
                           or_=or_, BATCH_SIZE=20, CLAIM_SECONDS=900, MAX_BACKOFF_SECONDS=900)
        fn.__globals__["TempTrip"] = TemporaryBooking
        from sqlalchemy import select
        fn.__globals__["select"] = select
        return fn

    async def test_only_due_payment_linked_unresolved_bookings_are_claimed(self):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        self.add("due", {"configured_provider_order_id": "order_1"})
        self.add("unpaid_no_order", {})
        self.add("other_provider", {"another_provider_order_id": "order_2"})
        self.add("review", {"configured_provider_order_id": "order_3", "reconciliation_state": "review_required"})
        self.add("booked", {"configured_provider_order_id": "order_4", "reconciliation_state": "booked"})
        self.add("not_due", {"configured_provider_order_id": "order_5", "reconciliation_next_check_at": future})
        claim = self.function("_claim_bookings")
        self.assertEqual(await claim(self.db), [("due", "customer")])
        self.assertEqual(await claim(self.db), [])
        sql = str(self.statements[0].compile(dialect=mysql.dialect()))
        self.assertIn("FOR UPDATE SKIP LOCKED", sql)

    async def test_bounded_batches_do_not_starve_other_bookings(self):
        for identifier, age in (("oldest", 3), ("middle", 2), ("newest", 1)):
            self.add(identifier, {"configured_provider_order_id": identifier}, age)
        claim = self.function("_claim_bookings")
        self.assertEqual(await claim(self.db, 1), [("oldest", "customer")])
        self.assertEqual(await claim(self.db, 1), [("middle", "customer")])
        self.assertEqual(await claim(self.db, 1), [("newest", "customer")])

    async def test_expired_claim_is_recoverable(self):
        self.add("expired", {"configured_provider_order_id": "order_1",
                             "reconciliation_next_check_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()})
        self.assertEqual(await self.function("_claim_bookings")(self.db), [("expired", "customer")])

    async def test_backoff_is_persisted_capped_and_preserves_payment_evidence(self):
        booking = self.add("retry", {"configured_provider_order_id": "order_1", "payment_verified": True})
        schedule = self.function("_schedule_next_check")
        for expected_delay in (60, 120, 240, 480, 900, 900):
            before = datetime.now(timezone.utc)
            await schedule(self.db, "retry")
            self.session.refresh(booking)
            details = booking.payment_provider_metadata
            delay = (datetime.fromisoformat(details["reconciliation_next_check_at"]) - before).total_seconds()
            self.assertAlmostEqual(delay, expected_delay, delta=2)
            self.assertTrue(details["payment_verified"])

    async def test_review_flag_is_not_lost_when_rescheduling(self):
        booking = self.add("review", {"configured_provider_order_id": "order_1", "reconciliation_state": "review_required"})
        await self.function("_schedule_next_check")(self.db, "review")
        self.session.refresh(booking)
        self.assertEqual(booking.payment_provider_metadata["reconciliation_state"], "review_required")

    async def test_existing_manual_booking_is_excluded_after_processing(self):
        self.add("manual", {"configured_provider_order_id": "order_1"})
        await self.function("_schedule_next_check")(self.db, "manual", ReconciliationStateEnum.booked)
        self.assertEqual(await self.function("_claim_bookings")(self.db), [])

    async def test_consumed_temporary_booking_needs_no_reschedule(self):
        await self.function("_schedule_next_check")(self.db, "already_consumed")
        self.db.commit.assert_awaited_once()


class SchedulerRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_one_failed_booking_does_not_abort_the_batch(self):
        db = SimpleNamespace(rollback=AsyncMock())
        context = MagicMock()
        context.__aenter__ = AsyncMock(return_value=db)
        context.__aexit__ = AsyncMock(return_value=False)
        reconcile = AsyncMock(side_effect=[RuntimeError("provider unavailable"), SimpleNamespace(state=ReconciliationStateEnum.booked)])
        schedule = AsyncMock()
        run = load_function(
            "src/scheduler/tasks/reconcile_bookings.py", "_run_booking_reconciliation",
            BATCH_SIZE=20, AsyncSessionLocal=MagicMock(return_value=context),
            _claim_bookings=AsyncMock(return_value=[("first", "customer"), ("second", "customer")]),
            a_reconcile_booking=reconcile, _schedule_next_check=schedule)
        await run()
        self.assertEqual(reconcile.await_count, 2)
        schedule.assert_any_await(db, "first", None)
        schedule.assert_any_await(db, "second", ReconciliationStateEnum.booked)
        db.rollback.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
