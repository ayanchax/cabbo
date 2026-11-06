"""Add durable payment webhook inbox.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""
from alembic import op
import sqlalchemy as sa

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_webhook_events",
        sa.Column("provider", sa.String(32), primary_key=True),
        sa.Column("event_id", sa.String(255), primary_key=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("order_id", sa.String(64), nullable=False),
        sa.Column("payment_id", sa.String(64), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payment_webhooks_due", "payment_webhook_events", ["processed_at", "next_attempt_at"])


def downgrade():
    op.drop_index("ix_payment_webhooks_due", table_name="payment_webhook_events")
    op.drop_table("payment_webhook_events")
