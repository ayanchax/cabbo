import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    String,
    Float,
    DateTime,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base
from models.policies.refund_enum import PaymentProvider, RefundStatus, RefundTrigger, RefundType


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
        String(255), nullable=False, index=True, unique=True
    )  # ID of the entity for which the refund is being processed, e.g., trip ID, booking ID, etc.
    policy_id = Column( 
        String(255), nullable=True, index=True, unique=False
    ) # ID of the refund policy that was applied for this refund, if applicable, for example, cancellation policy ID, adjustment policy ID, dispute policy ID etc. This can help us track which kind of policy was applied for this refund and also can be used for reporting and analytics purposes to see which policies are being used more frequently for refunds and also to analyze the effectiveness of different refund policies in terms of customer satisfaction, financial impact, etc.
    refund_status = Column(
        SAEnum(RefundStatus), nullable=True, default=RefundStatus.unknown, comment="Status of the refund transaction from the payment provider, e.g., pending, completed, failed, etc."
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
        SAEnum(RefundType), nullable=False, default=RefundType.other
    )  # Type of refund, e.g., full, partial, etc.
    refund_provider = Column(
        SAEnum(PaymentProvider), nullable=True, comment="Payment provider used for processing the refund, e.g., Stripe, PayPal, etc."
    )  # Payment provider used for processing the refund, e.g., Stripe, PayPal, etc.
    refund_trigger=Column(
        SAEnum(RefundTrigger), nullable=True, default=RefundTrigger.automatic
    )  # Description of how the refund was triggered, e.g., "manual", "automatic"
    #Manual happens when refund got triggered manually by support team or finance team. Workflow happens when refund got triggered automatically by a workflow that was set up in the system, e.g., automatic refund for cancellations within free cancellation window, etc in the #refund_service.py where we have the logic to trigger refunds automatically based on certain conditions and criteria and when those conditions are met, the workflow will trigger and create a refund record in the refunds table with refund_trigger set to "workflow" and we can also have more details about the workflow that triggered the refund in the refund_details field as well if needed.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    created_by = Column(
        MySQL_CHAR(36), nullable=True
    )  # User ID of the admin or system that created the refund record
    
    # Flag to indicate if the refund record is active or has been soft-deleted
    is_active = Column(Boolean, nullable=False, default=True)

    trip = relationship(
        "Trip",
        primaryjoin="Refund.entity_id==Trip.id",
        foreign_keys="[Refund.entity_id]",
        uselist=False,
        back_populates="refund",
    )  # One-to-one relationship to Trip table based on entity_id, which is populated when a refund is initiated for the trip and the refund record is created in the refunds table.
