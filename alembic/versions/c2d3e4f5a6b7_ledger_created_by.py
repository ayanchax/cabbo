"""Track who created collection and refund ledger records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import CHAR

revision = "c2d3e4f5a6b7"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None

TABLES = ("platform_fee_collections", "platform_fee_refund_adjustments")


def upgrade():
    for table in TABLES:
        op.add_column(table, sa.Column(
            "created_by", CHAR(36), nullable=False, server_default="system",
            comment="Creator user ID for manual/backfill entries; system for automated entries.",
        ))


def downgrade():
    for table in reversed(TABLES):
        op.drop_column(table, "created_by")
