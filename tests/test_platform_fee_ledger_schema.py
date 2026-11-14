"""Exercise the ledger migration without application settings or a live database."""
import ast
from pathlib import Path
import runpy
import unittest
import asyncio
import sys
from types import SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import Session


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class PlatformFeeLedgerSchemaTests(unittest.TestCase):
    def setUp(self):
        self.engine = sa.create_engine("sqlite://")
        self.connection = self.engine.connect()
        self.connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        self.base = declarative_base()
        for table in ("trips", "refunds", "tax_configurations", "customers"):
            sa.Table(table, self.base.metadata, sa.Column("id", sa.String(36), primary_key=True))
        self.base.metadata.create_all(self.connection)
        self.connection.execute(self.base.metadata.tables["trips"].insert(), {"id": "trip-1"})
        self.connection.execute(self.base.metadata.tables["customers"].insert(), {"id": "customer-1"})
        self.models = {"Base": self.base}
        for filename in ("invoice_orm.py", "platform_fee_ledger_orm.py"):
            tree = ast.parse((ROOT / "src/models/financial" / filename).read_text())
            tree.body = [node for node in tree.body if not (
                isinstance(node, ast.ImportFrom) and node.module == "db.database"
            )]
            exec(compile(tree, filename, "exec"), self.models)
        self.migration = runpy.run_path(str(ROOT / "alembic/versions/e8f9a0b1c2d3_platform_fee_tax_ledger.py"))
        self.operations = Operations(MigrationContext.configure(self.connection))
        self.migration["upgrade"].__globals__["op"] = self.operations
        self.migration["upgrade"]()
        self.customer_migration = runpy.run_path(str(ROOT / "alembic/versions/a0b1c2d3e4f5_ledger_customer_foreign_key.py"))
        self.customer_migration["upgrade"].__globals__["op"] = self.operations
        self.customer_migration["upgrade"]()

    def tearDown(self):
        self.connection.close()
        self.engine.dispose()

    def test_migration_matches_model_columns_and_indexes(self):
        inspector = sa.inspect(self.connection)
        for table_name in ("invoices", "platform_fee_collections", "platform_fee_refund_adjustments"):
            model_table = self.base.metadata.tables[table_name]
            columns = {column["name"]: column for column in inspector.get_columns(table_name)}
            self.assertEqual(set(columns), set(model_table.columns.keys()))
            for column in model_table.columns:
                self.assertTrue(column.comment, column.name)
                self.assertEqual(columns[column.name]["nullable"], column.nullable)
                self.assertEqual(str(columns[column.name]["type"]), str(column.type))
            self.assertEqual(
                {index["name"] for index in inspector.get_indexes(table_name)},
                {index.name for index in model_table.indexes},
            )
            self.assertEqual(
                {(tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
                 for fk in inspector.get_foreign_keys(table_name)},
                {((fk.parent.name,), fk.column.table.name, (fk.column.name,))
                 for fk in model_table.foreign_keys},
            )

    def test_duplicate_payment_and_trip_deletion_are_rejected(self):
        table = self.base.metadata.tables["platform_fee_collections"]
        from datetime import datetime, timezone
        row = dict(entity_id="trip-1", provider="razorpay", payment_id="pay-1", order_id="order-1",
                   payment_status="captured", currency="INR", captured_amount="118.00",
                   captured_at=datetime.now(timezone.utc), customer_id="customer-1", platform_fee_base="100.00",
                   platform_fee_tax="18.00", platform_fee_gross="118.00", source="reconciliation")
        self.connection.execute(table.insert(), row)
        with self.assertRaises(sa.exc.IntegrityError):
            self.connection.execute(table.insert(), row)
        with self.assertRaises(sa.exc.IntegrityError):
            self.connection.execute(self.base.metadata.tables["trips"].delete())
        with self.assertRaises(sa.exc.IntegrityError):
            self.connection.execute(table.update().values(invoice_id="missing-invoice"))
        with self.assertRaises(sa.exc.IntegrityError):
            self.connection.execute(self.base.metadata.tables["customers"].delete())
        with self.assertRaises(sa.exc.IntegrityError):
            self.connection.execute(table.update().values(customer_id="missing-customer"))

    def test_downgrade_preserves_existing_tables(self):
        self.customer_migration["downgrade"].__globals__["op"] = self.operations
        self.customer_migration["downgrade"]()
        self.migration["downgrade"].__globals__["op"] = self.operations
        self.migration["downgrade"]()
        self.assertEqual(set(sa.inspect(self.connection).get_table_names()),
                         {"trips", "refunds", "tax_configurations", "customers"})

    def test_collection_snapshot_repair_and_repeat_are_idempotent(self):
        tree = ast.parse((ROOT / "src/services/platform_fee_ledger_service.py").read_text())
        tree.body = [node for node in tree.body if not (
            isinstance(node, ast.ImportFrom) and node.module.startswith("models.")
        )]
        scope = {"PlatformFeeCollection": self.models["PlatformFeeCollection"], "Trip": object,
                 "ReconciliationStateEnum": SimpleNamespace(captured=SimpleNamespace(value="captured"))}
        exec(compile(tree, "ledger_service", "exec"), scope)
        trip = SimpleNamespace(id="trip-1", payment_provider="razorpay", payment_order_id="order-1",
            advance_payment=118, creator_id="customer-1", payment_provider_metadata={
                "razorpay_payment_id": "pay-1", "payment_verified": True, "currency": "INR"},
            price_breakdown={"platform_fee_base": 100, "platform_fee_tax": 18,
                             "platform_fee_tax_rate_percent": 18, "platform_fee_tax_type": "GST"})
        session = Session(bind=self.connection)

        class Adapter:
            async def execute(self, query):
                return session.execute(query)

            def add(self, row):
                session.add(row)

            async def flush(self):
                session.flush()

        async def exercise():
            ensure = scope["a_ensure_platform_fee_collection"]
            first = await ensure(trip, Adapter())
            self.assertEqual(first.platform_fee_base, 100)
            self.assertEqual(first.platform_fee_tax, 18)
            self.assertIsNone(first.captured_at)
            self.assertTrue(first.review_required)
            # A later changed trip/config cannot rewrite the original snapshot.
            trip.price_breakdown["platform_fee_tax"] = 99
            self.assertIs(await ensure(trip, Adapter()), first)
            self.assertEqual(first.platform_fee_tax, 18)
            trip.payment_provider_metadata["razorpay_payment_id"] = "pay-2"
            unresolved = await ensure(trip, Adapter())
            self.assertIsNone(unresolved.platform_fee_base)
            self.assertIn("tax_breakdown_unresolved", unresolved.review_reason)
            trip.payment_provider_metadata["razorpay_payment_id"] = "pay-3"
            trip.payment_provider_metadata["payment_verified"] = False
            self.assertIsNone(await ensure(trip, Adapter()))
            self.assertEqual(session.query(self.models["PlatformFeeCollection"]).count(), 2)

        try:
            asyncio.run(exercise())
        finally:
            session.close()


if __name__ == "__main__":
    unittest.main()
