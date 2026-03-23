#State or Province ORM model
from sqlalchemy import Boolean, Column, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from core.security import RoleEnum
from db.database import Base
import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from datetime import datetime, timezone

class StateModel(Base):
    __tablename__ = "states_master"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False, index=True)
    state_name = Column(String(128), nullable=False, unique=True) # e.g. Karnataka
    state_code = Column(String(16), nullable=False, unique=True, index=True) # e.g. KA
    country_id = Column(String(36), ForeignKey("countries_master.id", ondelete="CASCADE"), nullable=False, index=True)

    # relationships 1 state has 1 country
    country = relationship("CountryModel", back_populates="states")
    # 1 State has many Regions
    regions = relationship("RegionModel", back_populates="state", cascade="all, delete-orphan", lazy="selectin")
    is_serviceable = Column(Boolean, nullable=False, default=True)
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_modified = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )