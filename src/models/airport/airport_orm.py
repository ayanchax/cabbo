from sqlalchemy import Boolean, Column, String, DateTime, Enum as SAEnum, func, Float
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
import uuid
from core.security import RoleEnum
from db.database import Base
from datetime import datetime, timezone

class AirportModel(Base):
    __tablename__ = "airports_master"

    id = Column(MySQL_CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    display_name = Column(String(255), nullable=False)
    iata_code = Column(String(8), nullable=True)
    icao_code = Column(String(8), nullable=True)
    elevation_ft = Column(String(16), nullable=True)
    timezone = Column(String(64), nullable=True)
    dst = Column(String(8), nullable=True)
    tz_database_time_zone = Column(String(64), nullable=True)
    type = Column(String(32), nullable=True)
    source = Column(String(64), nullable=True)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    place_id = Column(String(128), nullable=False, unique=True)
    address = Column(String(512), nullable=False)
    country = Column(String(64), nullable=True)
    country_code = Column(String(8), nullable=True)
    state = Column(String(64), nullable=True)
    state_code = Column(String(8), nullable=True)
    region = Column(String(64), nullable=True)
    region_code = Column(String(8), nullable=False, index=True) #Region code is a non nullable field as it is used to populate region-wise airport locations in RegionModel
    postal_code = Column(String(16), nullable=True)
    is_serviceable = Column(Boolean, nullable=False, default=True)
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_modified = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # One or more airports belong to one region