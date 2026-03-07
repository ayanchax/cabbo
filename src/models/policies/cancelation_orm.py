from sqlalchemy import (
    Boolean,
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
)
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from db.database import Base
from core.security import RoleEnum
from sqlalchemy import Enum as SAEnum

from models.trip.trip_enums import CancellationSubStatusEnum


class CancellationPolicy(Base):
    __tablename__ = "cancellation_policies"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type_id = Column(
        MySQL_CHAR(36), ForeignKey("trip_types_master.id"), nullable=False, index=True
    )
    # Since cancellation policies like cut off time, trip-wise cancelation amount may vary by region in local or airport trips
    region_id = Column(
        MySQL_CHAR(36), ForeignKey("regions_master.id"), nullable=True, index=True
    )
    # Since cancellation policies like cut off time, trip-wise cancelation amount may vary by state of origin in intercity trips
    state_id = Column(
        MySQL_CHAR(36), ForeignKey("states_master.id"), nullable=True, index=True
    )
    # free cancellation cutoff in minutes (e.g. 30, 120, 1440)
    free_cutoff_minutes = Column(Integer, nullable=False, default=0)
    free_cutoff_time_label = Column(
        String(50), nullable=True
    )  # e.g. '30 minutes before', '2 hours before'

    refund_percentage = Column(
        Float, nullable=False, default=0.0
    )  # Percentage of the fare to be refunded against advance payment. 100% refund if cancellation is made from our end or by customer on or before the free cutoff time. Partial refund if cancellation is made after the free cutoff time. For example, 100.0 for full refund, 50.0 for half refund, 0.0 for no refund.
    is_active = Column(Boolean, nullable=False, default=True)

    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


class Cancellation(Base):
    __tablename__ = "trip_cancellations"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    entity_id = Column(
        MySQL_CHAR(36), nullable=False, index=True, unique=True
    )  # ID of the associated trip for which cancellation record is being created
    canceled_by = Column(
        MySQL_CHAR(36), nullable=False
    )  # user_id of the person who canceled the trip or 'system' if canceled by the system
    cancellation_sub_status = Column(
        SAEnum(CancellationSubStatusEnum, name="cancellation_sub_status_enum"),
        nullable=False,
        default=CancellationSubStatusEnum.none,
    )
    reason = Column(
        String(255), nullable=True
    )  # Reason for cancellation provided by the customer or system user/admin

    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    updated_at = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )
    is_active = Column(Boolean, nullable=False, default=True)
    trip = relationship(
        "Trip",
        primaryjoin="Cancellation.entity_id==Trip.id",
        foreign_keys="[Cancellation.entity_id]",
        uselist=False,
        back_populates="cancellation",
    )
