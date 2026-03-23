import uuid
from sqlalchemy import Column
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    String,
    DateTime,
    Enum as SAEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base
from models.policies.dispute_enum import DisputeTriggerEnum, DisputeTypeEnum
from models.policies.dispute_schema import DisputeDetailsSchema
from models.support.support_enum import TicketStatusEnum
from datetime import datetime, timezone


class Dispute(Base):
    __tablename__ = "disputes"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )  # UUID for the dispute
    entity_id = Column(
        MySQL_CHAR(36), nullable=False, unique=True
    )  # ID of the associated trip
    reason = Column(String(255), nullable=False)  # Reason for the dispute
    dispute_type = Column(
        SAEnum(DisputeTypeEnum),
        nullable=False,
        default=DisputeTypeEnum.unknown,
        comment="Type of dispute, e.g., fare, service, etc.",
    )  # Type of dispute, e.g., fare, service, etc.
    comments = Column(
        JSON, nullable=True
    )  # Additional comments or details between customer and support regarding the dispute
    details: DisputeDetailsSchema = Column(
        JSON, nullable=True
    )  # Additional details about the dispute DisputeDetailsSchema
    raised_by = Column(
        MySQL_CHAR(36), nullable=False
    )  # User ID of the person who raised the dispute
    status = Column(
        SAEnum(TicketStatusEnum), nullable=False, default=TicketStatusEnum.open
    )  # Status of the dispute (e.g., open, resolved, rejected)
    dispute_trigger = Column(
        SAEnum(DisputeTriggerEnum),
        nullable=True,
        comment="Description of how the dispute was triggered, e.g., 'manual', 'automatic'",
        default=DisputeTriggerEnum.automatic,
    )  # Description of how the dispute was triggered, e.g., "manual", "automatic"
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    
    is_active = Column(
        Boolean, nullable=False, default=True
    )  # Flag to indicate if the dispute record is active or has been soft-deleted
    # A dispute is associated with a trip, and a trip can have one dispute associated with it, which is populated when a dispute is raised for the trip, so the relationship is one-to-one from Trip to Dispute and many-to-one from Dispute to Trip.
    trip = relationship(
        "Trip",
        primaryjoin="Dispute.entity_id==Trip.id",
        foreign_keys="[Dispute.entity_id]",
        uselist=False,
        back_populates="dispute",
    )
