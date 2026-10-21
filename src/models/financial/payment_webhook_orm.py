from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Index, Integer, String
from db.database import Base


class PaymentWebhookEvent(Base):
    """Durable inbox; stores identifiers only, never the raw customer payload."""
    __tablename__ = "payment_webhook_events"
    __table_args__ = (Index("ix_payment_webhooks_due", "processed_at", "next_attempt_at"),)

    provider = Column(String(32), primary_key=True)
    event_id = Column(String(255), primary_key=True)
    event_type = Column(String(64), nullable=False)
    order_id = Column(String(64), nullable=False)
    payment_id = Column(String(64), nullable=False)
    body_hash = Column(String(64), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True), nullable=True)
