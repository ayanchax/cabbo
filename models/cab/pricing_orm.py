from enum import Enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    ForeignKey,
    DateTime,
    Enum as SAEnum,
)
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
import uuid
from db.database import Base
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum
from sqlalchemy.sql import func
from core.security import RoleEnum


# Pricing models for different cab types and fuel types
# Since cab types and fuel types are related to trip pricing, they are defined here
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
    cab_names = Column(
        String(255), nullable=True
    )  # Comma-separated example cab model names
    inventory_cab_names = Column(
        String(255), nullable=True
    )  # Comma-separated actual inventory cab model names
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


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
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


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
    cab_type_id = Column(
        MySQL_CHAR(36), ForeignKey("cab_types_master.id"), nullable=False
    )
    fuel_type_id = Column(
        MySQL_CHAR(36), ForeignKey("fuel_types_master.id"), nullable=False
    )
    base_fare_per_km = Column(Float, nullable=False)
    driver_allowance_per_day = Column(Float, nullable=False)
    # Overage config fields
    min_included_km_per_day = Column(
        Integer, nullable=False, default=300
    )  # 200 for hatchback, 300 for others
    overage_per_km = Column(Float, nullable=False)
    night_overage_per_block = Column(Float, nullable=False, default=100)
    night_block_hours = Column(Integer, nullable=False, default=3)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


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
    cab_type_id = Column(
        MySQL_CHAR(36), ForeignKey("cab_types_master.id"), nullable=False
    )
    fuel_type_id = Column(
        MySQL_CHAR(36), ForeignKey("fuel_types_master.id"), nullable=False
    )
    hourly_rate = Column(Float, nullable=False)
    # Overage config fields
    min_included_hours = Column(Integer, nullable=False, default=4)
    max_included_hours = Column(Integer, nullable=False, default=12)
    overage_per_hour = Column(Float, nullable=False)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


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
    cab_type_id = Column(
        MySQL_CHAR(36), ForeignKey("cab_types_master.id"), nullable=False
    )
    fuel_type_id = Column(
        MySQL_CHAR(36), ForeignKey("fuel_types_master.id"), nullable=False
    )
    airport_fare_per_km = Column(Float, nullable=False)
    # Overage config fields
    max_included_km = Column(Integer, nullable=False, default=42)
    overage_per_km = Column(Float, nullable=False)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


# Toll and parking pricing
class TollParkingConfig(Base):
    __tablename__ = "toll_parking_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type = Column(
        SAEnum(TripTypeEnum), nullable=False
    )  # local, airport, outstation
    toll = Column(Float, nullable=True)  # For local/airport
    parking = Column(Float, nullable=True)  # For local/airport
    toll_per_block = Column(Float, nullable=True)  # For outstation
    parking_per_block = Column(Float, nullable=True)  # For outstation
    block_days = Column(Integer, nullable=True)  # For outstation
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )
    # All fields except trip_type are nullable, so this table can flexibly store any trip-type-specific fixed rates
    # This table is independent of cab/fuel type, as these are global/fixed rates per trip type


# Overage pricing warning configuration
class OverageWarningConfig(Base):
    __tablename__ = "overage_warning_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type = Column(SAEnum(TripTypeEnum), nullable=False, unique=True)
    warning_km_threshold = Column(Float, nullable=False)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


# Night charge pricing configuration
class NightChargeConfig(Base):
    __tablename__ = "night_charge_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    night_start_hour = Column(Integer, nullable=False)  # 24-hr format, e.g., 20 for 8PM
    night_end_hour = Column(Integer, nullable=False)  # 24-hr format, e.g., 6 for 6AM
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )
