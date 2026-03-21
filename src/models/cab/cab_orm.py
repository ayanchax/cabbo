from sqlalchemy import (
    JSON,
    Column,
    String,
    DateTime,
    Enum as SAEnum,
    Boolean
)
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
import uuid


from db.database import Base
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum
from sqlalchemy.sql import func
from core.security import RoleEnum



class CabType(Base):
    __tablename__ = "cab_types_master"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    name = Column(SAEnum(CarTypeEnum), unique=True, nullable=False)
    description = Column(String(255), nullable=True)  # Description of cab type
    capacity = Column(String(20), nullable=True)  # Passenger capacity e.g, "4+1",
    cab_names = Column(
        JSON, nullable=True
    )  # JSON list of cab model names
    inventory_cab_names = Column(
        JSON, nullable=True
    )  # JSON list of actual inventory cab model names
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )
    is_active=Column(Boolean, nullable=False, default=True)


class FuelType(Base):
    __tablename__ = "fuel_types_master"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    name = Column(SAEnum(FuelTypeEnum), unique=True, nullable=False)
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )
    is_active=Column(Boolean, nullable=False, default=True)
