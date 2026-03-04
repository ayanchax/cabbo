import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import (
    JSON,
    Column,
    String,
    Float,
    DateTime,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base


class Refund(Base):
    __tablename__ = "refunds"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    entity_id = Column(
        String(255), nullable=False, index=True
    )  # ID of the entity for which the refund is being processed, e.g., trip ID, booking ID, etc.
    refund_status = Column(
        String(50), nullable=True
    )  # Status of the refund transaction from the payment provider, e.g., pending, completed, failed, etc.
    refund_amount = Column(
        Float, nullable=False
    )  # Amount to be refunded to the customer
    refund_reason = Column(
        String(255), nullable=False
    )  # Reason for the refund (e.g., cancellation, adjustment, etc.)
    refund_details = Column(
        JSON, nullable=True
    )  # Details of the refund transaction from the payment provider
    refund_initiated_datetime = Column(
        DateTime, nullable=True
    )  # Date and time when the refund was initiated
    refund_type = Column(
        String(50), nullable=True
    )  # Type of refund, e.g., full, partial, etc.
    refund_provider = Column(
        String(50), nullable=True
    )  # Payment provider used for processing the refund, e.g., Stripe, PayPal, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(
        MySQL_CHAR(36), nullable=True
    )  # User ID of the admin or system that created the refund record
    trip = relationship(
        "Trip",
        primaryjoin="Refund.entity_id==Trip.id",
        foreign_keys="[Refund.entity_id]",
        uselist=False,
        back_populates="refund",
    )  # One-to-one relationship to Trip table based on entity_id, which is populated when a refund is initiated for the trip and the refund record is created in the refunds table.
