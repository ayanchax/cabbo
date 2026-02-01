from sqlalchemy import (
    Boolean,
    Column,
    Index,
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


# Night charge pricing configuration, can be applied to all trip types but mostly used for outstation trips and local trips, hence we have state_id and region_id both optional
# We are keeping this separate from CommonPricingConfiguration since night charges may vary by region/state
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

# Trip type wise pricing configuration. These are common configurations applicable to all cab types, fuel types for a given trip type
# and are referenced in the trip fare calculation logic
# They are different from NightPricingConfiguration which is mainly for night surcharge related settings
# They are different from FixedPlatformPricingConfiguration which is mainly for fixed platform fee per booking
# They are different from PermitFeeConfiguration which is mainly for permit fee per state, cab type and fuel type
class CommonPricingConfiguration(Base):
    __tablename__ = "tripwise_pricing_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type_id = Column(
        MySQL_CHAR(36), ForeignKey("trip_types_master.id"), nullable=False
    )  # FK to TripTypeMaster.id
    dynamic_platform_fee_percent = Column(Float, nullable=False)  #The dynamic platform fee as percentage of total fare is applied to the trip type per booking per region. We need this to support different platform fee percentages for different trip types. E.g, airport trips may have lower platform fee percentage than local trips in one region, while in another region it may be different, based on the economics of that region. This dynamic platform fee percentage is a convenience fee charged to the customer to cover the cost of operating the platform for that trip type in that region.
    
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


# Fixed Platform fee for cost to serve per booking, like payment gateway fee, SMS fee, customer database management cost etc.
class FixedPlatformPricingConfiguration(Base):
    __tablename__ = "fixed_platform_pricing"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    # Add country_id for country-specific platform fees
    country_id = Column(
        MySQL_CHAR(36), 
        ForeignKey("countries_master.id"), 
        nullable=True,  # Nullable for backward compatibility or "default" fee
        index=True,
        unique=True,
        comment="FK to countries_master; null means applies to all countries"

    )
    # The fixed platform fee as a flat amount per booking, e.g., payment gateway fee, SMS fee, customer database management cost etc.
    
    # This is different from dynamic platform fee percentage which is calculated as percentage of total fare and serves as a convenience fee charged to the customer to cover the cost of operating the platform for that trip type in that region.
    
    # Fixed Platform fee = Cost of serving per booking in the platform.
    # Dynamic Platform fee = Percentage of total fare charged to customer to cover platform operations for that trip type in that region
    
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
# Since Permit fee varies by state, cab type and fuel type, we have those foreign keys as well and hence we cannot keep these settings in the CommonPricingConfiguration table
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
