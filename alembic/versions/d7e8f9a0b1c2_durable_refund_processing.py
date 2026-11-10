"""Durable refund retries and independent notification tracking.

Deploy before the new refund worker. Old rows keep their existing primary keys.
"""
from alembic import op
import sqlalchemy as sa

revision = "d7e8f9a0b1c2"
down_revision = "8d449d9188f3"
branch_labels = None
depends_on = None


def upgrade():
    for column in (
        sa.Column("provider_refund_id", sa.String(64), nullable=True),
        sa.Column("payment_id", sa.String(64), nullable=True),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_error", sa.String(255), nullable=True),
        sa.Column("cancellation_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processed_notified_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("refunds", column)
    op.create_unique_constraint("uq_refunds_provider_refund_id", "refunds", ["provider_refund_id"])
    op.create_unique_constraint("uq_refunds_idempotency_key", "refunds", ["idempotency_key"])
    op.create_index("ix_refunds_due", "refunds", ["is_active", "review_required", "next_attempt_at"])
    # Historical emails may already have been delivered; avoid replaying them on
    # deployment. Pending legacy rows recover provider/payment IDs in the worker.
    op.execute(sa.text("UPDATE refunds SET cancellation_notified_at = CURRENT_TIMESTAMP"))
    op.execute(sa.text("UPDATE refunds SET processed_notified_at = CURRENT_TIMESTAMP "
                       "WHERE refund_status IN ('processed', 'completed')"))


def downgrade():
    op.drop_index("ix_refunds_due", table_name="refunds")
    op.drop_constraint("uq_refunds_idempotency_key", "refunds", type_="unique")
    op.drop_constraint("uq_refunds_provider_refund_id", "refunds", type_="unique")
    for name in ("processed_notified_at", "cancellation_notified_at", "last_error",
                 "review_required", "next_attempt_at", "attempts", "idempotency_key",
                 "payment_id", "provider_refund_id"):
        op.drop_column("refunds", name)
