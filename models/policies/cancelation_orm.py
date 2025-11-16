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
from core.constants import APP_COUNTRY_CURRENCY, APP_COUNTRY_CURRENCY_SYMBOL
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
    # free cancellation cutoff in minutes (e.g. 30, 120, 1440)
    free_cutoff_minutes = Column(Integer, nullable=False, default=0)
    free_cutoff_time_label = Column(String(50), nullable=True)  # e.g. '30 minutes before', '2 hours before'

    fee_amount = Column(Float, nullable=False, default=0.0)  # cancellation fee amount
    currency = Column(String(8), nullable=True, default=APP_COUNTRY_CURRENCY)
    currency_symbol = Column(String(8), nullable=True, default=APP_COUNTRY_CURRENCY_SYMBOL)
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())