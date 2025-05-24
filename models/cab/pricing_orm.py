from enum import Enum
from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, Enum as SAEnum
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
import uuid
from db.database import Base
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from datetime import datetime
from sqlalchemy.sql import func


class RoleEnum(str, Enum):
    system_admin = "system_admin"
    driver_admin = "driver_admin"
    finance_admin = "finance_admin"
    system = "system"


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
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(DateTime, nullable=False, default=func.utc_timestamp(), onupdate=func.utc_timestamp())


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
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(DateTime, nullable=False, default=func.utc_timestamp(), onupdate=func.utc_timestamp())


# Outstation pricing
class OutstationCabPricing(Base):
    __tablename__ = "outstation_cab_pricing"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    cab_type_id = Column(MySQL_CHAR(36), ForeignKey("cab_types_master.id"), nullable=False)
    fuel_type_id = Column(MySQL_CHAR(36), ForeignKey("fuel_types_master.id"), nullable=False)
    base_fare_per_km = Column(Float, nullable=False)
    driver_allowance_per_day = Column(Float, nullable=False)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(DateTime, nullable=False, default=func.utc_timestamp(), onupdate=func.utc_timestamp())


# Local pricing
class LocalCabPricing(Base):
    __tablename__ = "local_cab_pricing"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    cab_type_id = Column(MySQL_CHAR(36), ForeignKey("cab_types_master.id"), nullable=False)
    fuel_type_id = Column(MySQL_CHAR(36), ForeignKey("fuel_types_master.id"), nullable=False)
    hourly_rate = Column(Float, nullable=False)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(DateTime, nullable=False, default=func.utc_timestamp(), onupdate=func.utc_timestamp())


# Airport pricing
class AirportCabPricing(Base):
    __tablename__ = "airport_cab_pricing"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    cab_type_id = Column(MySQL_CHAR(36), ForeignKey("cab_types_master.id"), nullable=False)
    fuel_type_id = Column(MySQL_CHAR(36), ForeignKey("fuel_types_master.id"), nullable=False)
    airport_fare_per_km = Column(Float, nullable=False)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(DateTime, nullable=False, default=func.utc_timestamp(), onupdate=func.utc_timestamp())


class TollParkingConfig(Base):
    __tablename__ = "toll_parking_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type = Column(SAEnum(TripTypeEnum), nullable=False)  # local, airport, outstation
    toll = Column(Float, nullable=True)  # For local/airport
    parking = Column(Float, nullable=True)  # For local/airport
    toll_per_block = Column(Float, nullable=True)  # For outstation
    parking_per_block = Column(Float, nullable=True)  # For outstation
    block_days = Column(Integer, nullable=True)  # For outstation
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(DateTime, nullable=False, default=func.utc_timestamp(), onupdate=func.utc_timestamp())
    # All fields except trip_type are nullable, so this table can flexibly store any trip-type-specific fixed rates
    # This table is independent of cab/fuel type, as these are global/fixed rates per trip type
