"""Atomic transaction and ordinary payment identity column regressions."""
import ast
from datetime import datetime, timedelta, timezone
import json
import runpy
from types import SimpleNamespace
from typing import Optional
import unittest
from unittest.mock import AsyncMock, MagicMock

from pydantic import BaseModel
from sqlalchemy import (Column, Enum, DateTime, ForeignKey, Integer, JSON,
                        String, UniqueConstraint, and_, create_engine, event, or_, select, text)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, declarative_base
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import mysql

from test_temp_trip_cleanup import ROOT, load_function
from test_booking_reconciliation import BookingError
from models.trip.trip_enums import TripStatusEnum
from models.policies.refund_enum import PaymentProvider

Base = declarative_base()


class TemporaryTrip(Base):
    __tablename__ = "temp_trips"
    id = Column(String(64), primary_key=True)
    creator_id = Column(String(64))
    trip_type_id = Column(String(64))
    start_datetime = Column(DateTime)
    platform_fee = Column(Integer)
    final_price = Column(Integer)
    payment_provider_metadata = Column(JSON)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return None  # Other optional trip properties are irrelevant to these transactions.


class FinalTrip(Base):
    __tablename__ = "trips"
    __table_args__ = (UniqueConstraint("payment_provider", "payment_order_id", name="uq_trips_payment_order"),)
    id = Column(String(64), primary_key=True)
    booking_id = Column(String(64))
    creator_id = Column(String(64))
    status = Column(String(64))
    payment_provider_metadata = Column(JSON)
    payment_provider = Column(Enum(PaymentProvider, name="payment_provider_enum"))
    payment_order_id = Column(String(255, collation="utf8mb4_bin"))

    def __init__(self, **kwargs):
        super().__init__(**{key: value for key, value in kwargs.items() if key in self.__mapper__.attrs})


class Audit(Base):
    __tablename__ = "trip_status_audit"
    id = Column(Integer, primary_key=True)
    trip_id = Column(String(64), ForeignKey("trips.id"), nullable=False)
    status = Column(String(64))
    committer_id = Column(String(64))
    reason = Column(String(64))


# Execute the actual TripCreate declaration with a minimal details type, avoiding app startup.
node = next(n for n in ast.parse((ROOT / "src/models/trip/trip_schema.py").read_text()).body
            if isinstance(n, ast.ClassDef) and n.name == "TripCreate")
schema_scope = dict(BaseModel=BaseModel, Optional=Optional, TripDetails=BaseModel,
                    TripStatusEnum=TripStatusEnum, RazorPayPaymentResponse=BaseModel)
exec(compile(ast.Module(body=[node], type_ignores=[]), "trip_schema.py", "exec"), schema_scope)
TripCreate = schema_scope["TripCreate"]


class AtomicFinalisationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        @event.listens_for(self.engine, "connect")
        def functions(connection, record):
            connection.create_collation("utf8mb4_bin", lambda left, right: (left > right) - (left < right))
            connection.execute("PRAGMA foreign_keys=ON")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine, expire_on_commit=False)
        self.db = SimpleNamespace(
            add=self.session.add, execute=AsyncMock(side_effect=self.session.execute),
            flush=AsyncMock(side_effect=self.session.flush), delete=AsyncMock(side_effect=self.session.delete),
            commit=AsyncMock(side_effect=self.session.commit), rollback=AsyncMock(side_effect=self.session.rollback),
            refresh=AsyncMock(side_effect=self.session.refresh),
        )
        self.temp = TemporaryTrip(id="temp_1", creator_id="customer", trip_type_id="local",
                                  start_datetime=datetime.now(timezone.utc) + timedelta(hours=2),
                                  platform_fee=153, final_price=1500,
                                  payment_provider_metadata={"razorpay_order_id": "order_1", "payment_verified": True})
        self.session.add(self.temp)
        self.session.commit()
        self.populate = AsyncMock(return_value={})

    def tearDown(self):
        self.session.close()
        self.engine.dispose()

    def fn(self, name, path="src/services/trips/booking_service.py", **dependencies):
        fn = load_function(path, name, TripCreate=TripCreate, RazorPayPaymentResponse=BaseModel,
                           settings=SimpleNamespace(PAYMENT_PROVIDER="razorpay", CABBO_DEFAULT_TIMEZONE="UTC", CABBO_DEFAULT_UTC_OFFSET=0),
                           TripStatusEnum=TripStatusEnum, TripStatusAudit=Audit, Optional=Optional,
                           a_populate_trip_schema=self.populate,
                           PAYMENT_VERIFIED_WITH_PENDING_CONFIRMATION="pending", TRIP_NOT_FOUND="missing",
                           TRIP_TYPE_ID_NOT_FOUND="invalid_type", **dependencies)
        fn.__globals__.update(Trip=FinalTrip, TempTrip=TemporaryTrip, select=select,
                              and_=and_, or_=or_, IntegrityError=IntegrityError, CabboException=BookingError)
        return fn

    def finalise(self):
        response = self.fn("a_booking_confirmation_response")
        existing_response = self.fn("a_existing_booking_response", a_booking_confirmation_response=response)
        return self.fn("a_create_confirmed_trip_from_temp_trip",
                       a_booking_confirmation_response=response, a_existing_booking_response=existing_response,
                       a_existing_booking=self.fn("a_existing_booking"),
                       a_get_trip_type_by_trip_type_id=AsyncMock(return_value=SimpleNamespace(name="local")),
                       a_generate_booking_id=AsyncMock(return_value="RENTAL-1"),
                       a_log_trip_audit=self.fn("a_log_trip_audit", "src/services/audit_trail_service.py"))

    def counts(self):
        return [len(self.session.execute(select(model)).scalars().all()) for model in (FinalTrip, Audit, TemporaryTrip)]

    async def test_success_is_one_commit_for_trip_audit_and_temp_deletion(self):
        result = await self.finalise()(self.temp, "admin", None, self.db)
        self.assertEqual(self.counts(), [1, 1, 0])
        self.assertEqual(result.trip_id, "temp_1")
        self.db.commit.assert_awaited_once()
        self.assertEqual(self.session.execute(select(Audit)).scalar_one().committer_id, "admin")

    async def test_audit_failure_rolls_back_trip_and_preserves_verified_temp(self):
        fn = self.finalise()
        fn.__globals__["a_log_trip_audit"] = AsyncMock(side_effect=RuntimeError("audit failed"))
        with self.assertRaises(BookingError):
            await fn(self.temp, "admin", None, self.db)
        self.assertEqual(self.counts(), [0, 0, 1])
        self.assertTrue(self.session.get(TemporaryTrip, "temp_1").payment_provider_metadata["payment_verified"])

    async def test_temp_deletion_failure_rolls_back_trip_and_audit(self):
        self.db.delete.side_effect = RuntimeError("delete failed")
        with self.assertRaises(BookingError):
            await self.finalise()(self.temp, "admin", None, self.db)
        self.assertEqual(self.counts(), [0, 0, 1])

    async def test_commit_failure_rolls_back_all_three_changes(self):
        self.db.commit.side_effect = RuntimeError("commit failed")
        with self.assertRaises(BookingError):
            await self.finalise()(self.temp, "admin", None, self.db)
        self.assertEqual(self.counts(), [0, 0, 1])

    async def test_response_failure_still_returns_durable_booking(self):
        self.populate.side_effect = RuntimeError("response failed")
        result = await self.finalise()(self.temp, "admin", None, self.db)
        self.assertEqual(self.counts(), [1, 1, 0])
        self.assertEqual(result.booking_id, "RENTAL-1")
        self.assertIsNone(result.trip_details)

    async def test_repeated_finalisation_returns_one_booking(self):
        fn = self.finalise()
        first = await fn(self.temp, "admin", None, self.db)
        # Simulate a worker retaining the original identifiers after another worker finishes.
        staged = SimpleNamespace(id="temp_1", creator_id="customer", payment_provider_metadata={"razorpay_order_id": "order_1"})
        second = await fn(staged, "admin", None, self.db)
        self.assertEqual(first.trip_id, second.trip_id)
        self.assertEqual(self.counts(), [1, 1, 0])

    async def test_order_already_assigned_to_other_owner_requires_review(self):
        self.session.add(FinalTrip(id="other", creator_id="someone_else", status="confirmed",
                                   payment_provider="razorpay", payment_order_id="order_1",
                                   payment_provider_metadata={"razorpay_order_id": "order_1"}))
        self.session.commit()
        with self.assertRaises(BookingError):
            await self.finalise()(self.temp, "admin", None, self.db)
        self.assertEqual(self.counts(), [1, 0, 1])
        details = self.session.get(TemporaryTrip, "temp_1").payment_provider_metadata
        self.assertEqual(details["reconciliation_reason"], "payment_order_already_assigned")

    async def test_unique_order_race_returns_existing_owned_booking(self):
        existing = FinalTrip(id="recovered", creator_id="customer", booking_id="RENTAL-EXISTING", status="confirmed",
                             payment_provider="razorpay", payment_order_id="order_1",
                             payment_provider_metadata={"razorpay_order_id": "order_1"})
        self.session.add(existing)
        self.session.commit()
        fn = self.finalise()
        # Simulate a conflicting insert appearing after the initial existence read.
        fn.__globals__["a_existing_booking"] = AsyncMock(side_effect=[None, existing])
        result = await fn(self.temp, "admin", None, self.db)
        self.assertEqual(result.trip_id, "recovered")
        self.assertEqual(self.counts(), [1, 0, 1])

    async def test_explicit_identity_blocks_duplicate_direct_sql_inserts(self):
        insert = text("INSERT INTO trips (id, payment_provider, payment_order_id) VALUES (:id, :provider, :order_id)")
        self.session.execute(insert, {"id": "first", "provider": "stripe", "order_id": "shared"})
        self.session.commit()
        with self.assertRaises(IntegrityError):
            self.session.execute(insert, {"id": "second", "provider": "stripe", "order_id": "shared"})
        self.session.rollback()

    async def test_different_providers_and_unpaid_trips_can_coexist(self):
        for index, provider in enumerate(("stripe", "phonepe", None, None)):
            self.session.add(FinalTrip(id=f"trip_{index}", payment_provider=provider,
                                      payment_order_id="shared" if provider else None))
        self.session.commit()
        self.assertEqual(len(self.session.execute(select(FinalTrip)).scalars().all()), 4)

    async def test_confirmation_populates_identity_columns(self):
        await self.finalise()(self.temp, "admin", None, self.db)
        trip = self.session.get(FinalTrip, "temp_1")
        self.assertEqual((trip.payment_provider, trip.payment_order_id), ("razorpay", "order_1"))
        self.session.expire(trip)
        self.assertIs(trip.payment_provider, PaymentProvider.razorpay)
        self.assertEqual(trip.payment_provider_metadata["razorpay_order_id"], "order_1")

    async def test_provider_order_identifiers_are_case_sensitive(self):
        for identifier in ("order_AbC", "order_aBc"):
            self.session.add(FinalTrip(id=identifier, payment_provider="razorpay", payment_order_id=identifier))
        self.session.commit()
        self.assertEqual(len(self.session.execute(select(FinalTrip)).scalars().all()), 2)

    def test_mysql_ddl_has_ordinary_columns_and_unique_order(self):
        ddl = str(CreateTable(FinalTrip.__table__).compile(dialect=mysql.dialect()))
        self.assertNotIn("GENERATED ALWAYS AS", ddl)
        self.assertIn("uq_trips_payment_order", ddl)

    async def test_strict_audit_errors_propagate_without_own_commit(self):
        self.db.flush.side_effect = RuntimeError("audit failed")
        with self.assertRaises(RuntimeError):
            await self.fn("a_log_trip_audit", "src/services/audit_trail_service.py")(
                db=self.db, trip_id="temp_1", status="confirmed", committer_id="admin",
                commit=False, raise_on_error=True)
        self.db.commit.assert_not_awaited()
        self.db.rollback.assert_not_awaited()

    def migration(self):
        migration = runpy.run_path(str(ROOT / "alembic/versions/c4d5e6f7a8b9_unique_trip_payment_order.py"))
        operations = MagicMock()
        operations.get_bind.return_value = self.session.connection()
        def add_column(table, column):
            self.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column.name} VARCHAR({column.type.length})"))
        operations.add_column.side_effect = add_column
        operations.create_unique_constraint.side_effect = lambda *args: self.session.execute(
            text("CREATE UNIQUE INDEX uq_trips_payment_order ON trips (payment_provider, payment_order_id)"))
        migration["upgrade"].__globals__["op"] = operations
        return migration, operations

    def raw_migration_table(self, rows):
        self.session.execute(text("DROP TABLE trip_status_audit"))
        self.session.execute(text("DROP TABLE trips"))
        self.session.execute(text("CREATE TABLE trips (id TEXT PRIMARY KEY, payment_provider_metadata TEXT)"))
        for index, metadata in enumerate(rows):
            self.session.execute(text("INSERT INTO trips VALUES (:id, :metadata)"),
                                 {"id": str(index), "metadata": json.dumps(metadata)})

    def test_migration_refuses_duplicates_before_schema_changes(self):
        self.raw_migration_table([{"razorpay_order_id": "duplicate"}, {"razorpay_order_id": "duplicate"}])
        migration, operations = self.migration()
        with self.assertRaisesRegex(RuntimeError, "Duplicate trip payment orders"):
            migration["upgrade"]()
        operations.add_column.assert_not_called()

    def test_migration_refuses_ambiguous_provider_metadata(self):
        self.raw_migration_table([{"razorpay_order_id": "one", "stripe_order_id": "two"}])
        migration, operations = self.migration()
        with self.assertRaisesRegex(RuntimeError, "multiple provider orders"):
            migration["upgrade"]()
        operations.add_column.assert_not_called()

    def test_migration_refuses_oversized_identifiers_before_ddl(self):
        self.raw_migration_table([{"razorpay_order_id": "x" * 256}])
        migration, operations = self.migration()
        with self.assertRaisesRegex(RuntimeError, "column limits"):
            migration["upgrade"]()
        operations.add_column.assert_not_called()

    def test_migration_backfills_existing_orders_and_builds_unique_index(self):
        self.raw_migration_table([{"razorpay_order_id": "old_order"}, {}])
        migration, operations = self.migration()
        migration["upgrade"]()
        self.assertEqual(operations.add_column.call_count, 2)
        row = self.session.execute(text("SELECT payment_provider, payment_order_id FROM trips WHERE id = '0'")).one()
        self.assertEqual(tuple(row), ("razorpay", "old_order"))
        with self.assertRaises(IntegrityError):
            self.session.execute(text("INSERT INTO trips (id, payment_provider, payment_order_id) VALUES ('duplicate', 'razorpay', 'old_order')"))
        self.session.rollback()
        operations.create_unique_constraint.assert_called_once_with(
            "uq_trips_payment_order", "trips", ["payment_provider", "payment_order_id"])

