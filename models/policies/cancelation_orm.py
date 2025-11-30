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
from sqlalchemy.sql import func
import uuid
from db.database import Base
from core.security import RoleEnum
from sqlalchemy import Enum as SAEnum

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
    free_cutoff_time_label = Column(String(50), nullable=True)  # e.g. '30 minutes before', '2 hours before'

    cancelation_amount = Column(Float, nullable=False, default=0.0)  # cancellation fee amount
     
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)


    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    updated_at = Column(DateTime, nullable=False, default=func.utc_timestamp(), onupdate=func.utc_timestamp())