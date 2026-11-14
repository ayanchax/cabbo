"""Allow unknown historical refund allocations and provider completion dates."""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a0b1c2d3e4f5"
branch_labels = None
depends_on = None


def upgrade():
    descriptions = {
        "refunded_base": "Cumulative refunded taxable fee base; null if any refund allocation is unresolved.",
        "refunded_tax": "Cumulative refunded GST; null if any refund allocation is unresolved.",
    }
    with op.batch_alter_table("platform_fee_collections") as batch:
        for name in ("refunded_base", "refunded_tax"):
            batch.alter_column(name, existing_type=sa.Numeric(18, 2), existing_server_default="0",
                               nullable=True, comment=descriptions[name])
    with op.batch_alter_table("platform_fee_refund_adjustments") as batch:
        batch.alter_column("processed_at", existing_type=sa.DateTime(timezone=True), nullable=True,
                           comment="UTC provider completion timestamp, null if unavailable; distinct from GST reporting date.")


def downgrade():
    # Refuse downgrade if it would require fabricating financial evidence.
    bind = op.get_bind()
    for table, predicate in (
        ("platform_fee_collections", "refunded_base IS NULL OR refunded_tax IS NULL"),
        ("platform_fee_refund_adjustments", "processed_at IS NULL"),
    ):
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table} WHERE {predicate}")).scalar_one():
            raise RuntimeError("Resolve unknown refund ledger values before downgrade")
    with op.batch_alter_table("platform_fee_refund_adjustments") as batch:
        batch.alter_column("processed_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    with op.batch_alter_table("platform_fee_collections") as batch:
        for name in ("refunded_base", "refunded_tax"):
            batch.alter_column(name, existing_type=sa.Numeric(18, 2), existing_server_default="0", nullable=False)
