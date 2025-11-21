from sqlalchemy import (
    Boolean,
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
from sqlalchemy.sql import func
from core.security import RoleEnum




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
    is_available_in_network = Column(
        Boolean, nullable=False, default=True
    )  # Indicates if this cab type is available for high-demand outstation trips
    overage_amount_per_km = Column(Float, nullable=False)
    # Since Outstation pricing may vary by state, we have the state_id foreign key here instead of region_id
    state_id = Column(
        MySQL_CHAR(36), ForeignKey("states_master.id"), nullable=True
    )  # FK to GeoStateModel.id
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
    overage_amount_per_hour = Column(Float, nullable=False)
    overage_amount_per_km = Column(Float, nullable=False)
    is_available_in_network = Column(
        Boolean, nullable=False, default=True
    )  # Indicates if this cab type is available for local trips
    region_id = Column(
        MySQL_CHAR(36), ForeignKey("regions_master.id"), nullable=True
    )
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
    fare_per_km = Column(Float, nullable=False)
    overage_amount_per_km = Column(Float, nullable=False)
    is_available_in_network = Column(
        Boolean, nullable=False, default=True
    )  # Indicates if this cab type is available for airport trips
    region_id = Column(
        MySQL_CHAR(36), ForeignKey("regions_master.id"), nullable=True
    )
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


# Night charge pricing configuration
class NightPricingConfiguration(Base):
    __tablename__ = "night_pricing_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    night_start_hour = Column(Integer, nullable=False)  # 24-hr format, e.g., 20 for 8PM
    night_end_hour = Column(Integer, nullable=False)  # 24-hr format, e.g., 6 for 6AM
    night_hours_label = Column(
        String(50), nullable=False, default="8 PM to 6 AM"
    )  # e.g., "8PM - 6AM"
    night_overage_amount_per_block = Column(
        Float, nullable=False, default=100
    )  # Applies to all trip types, but now mostly used for outstation
    night_block_hours = Column(
        Integer, nullable=False, default=1
    )  # Applies to all trip types, but now mostly used for outstation
    region_id = Column(
        MySQL_CHAR(36), ForeignKey("regions_master.id"), nullable=True
    )

    state_id = Column(
        MySQL_CHAR(36), ForeignKey("states_master.id"), nullable=True
    )
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


class TripwisePricingConfiguration(Base):
    __tablename__ = "tripwise_pricing_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type_id = Column(
        MySQL_CHAR(36), ForeignKey("trip_types_master.id"), nullable=False, unique=True
    )  # FK to TripTypeMaster.id
    dynamic_platform_fee_percent = Column(Float, nullable=False)  # e.g., 5.0 for 5%
    
    min_included_hours = Column(
        Integer, nullable=True, default=None
    )  # Local cab minimum included hours
    max_included_hours = Column(
        Integer, nullable=True, default=None
    )  # Local cab maximum included hours
    min_included_km = Column(
        Integer, nullable=True, default=None
    )  # For local cab minimum included km
    max_included_km = Column(
        Integer, nullable=True, default=None
    )  # For local cab maximum included km
    placard_charge = Column(
        Float, nullable=True
    )  # Only for airport pickup, can be null for others
    max_included_km = Column(
        Integer, nullable=True, default=None
    )  # For airport pickup/drop
    overage_warning_km_threshold = Column(
        Float, nullable=True
    )  # For airport pickup/drop and outstation
    toll = Column(Float, nullable=True)  # For airport pickup and drop
    parking = Column(Float, nullable=True)  # For airport pickup
    minimum_toll_wallet = Column(Float, nullable=True)  # For local/outstation
    minimum_parking_wallet = Column(Float, nullable=True)  # For local/outstation
    region_id = Column(
        MySQL_CHAR(36), ForeignKey("regions_master.id"), nullable=True  
    )
    state_id = Column(
        MySQL_CHAR(36), ForeignKey("states_master.id"), nullable=True
    )
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


# Fixed Platform fee for cost to serve per booking
class FixedPlatformPricing(Base):
    __tablename__ = "fixed_platform_pricing"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    fixed_platform_fee = Column(Float, nullable=False)  # e.g., 50.0 for ₹50
     
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


# Since Permit fee varies by state, so we have the state_id foreign key here instead of region_id
class PermitFeeConfiguration(Base):
    __tablename__ = "permit_fee_config"
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
    state_id = Column(
        MySQL_CHAR(36), ForeignKey("states_master.id"), nullable=False
    )  # FK to GeoStateModel.id
    

    permit_fee = Column(Float, nullable=False)  # Permit fee amount
    
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )
