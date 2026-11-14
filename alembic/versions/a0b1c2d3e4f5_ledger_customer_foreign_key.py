"""Protect customer references in platform-fee financial history."""
from alembic import op
import sqlalchemy as sa

revision = "a0b1c2d3e4f5"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None

CONSTRAINT_NAME = "fk_platform_fee_collection_customer"


def upgrade():
    # Do not silently erase historical references to make the constraint pass.
    orphan_count = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM platform_fee_collections AS ledger "
        "LEFT JOIN customers AS customer ON customer.id = ledger.customer_id "
        "WHERE ledger.customer_id IS NOT NULL AND customer.id IS NULL"
    )).scalar_one()
    if orphan_count:
        raise RuntimeError("Resolve orphaned platform-fee customer references before migrating")
    with op.batch_alter_table("platform_fee_collections") as batch:
        batch.create_foreign_key(CONSTRAINT_NAME, "customers", ["customer_id"], ["id"], ondelete="RESTRICT")


def downgrade():
    with op.batch_alter_table("platform_fee_collections") as batch:
        batch.drop_constraint(CONSTRAINT_NAME, type_="foreignkey")
