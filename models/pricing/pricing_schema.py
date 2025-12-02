from datetime import datetime
from pydantic import BaseModel, Field
from typing import List, Optional, Union

from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema



# Base schema for common trip pricing fields
class CabPricingBaseSchema(BaseModel):
    id: Optional[Union[int, str]]=Field(None, description="Unique identifier for the cab pricing record")  # Can be str (UUID) or int (DB ID)
    cab_type_id: Union[str, int] = Field(..., description="Identifier for the cab type")  # Can be str (UUID) or int (DB ID)
    fuel_type_id: Union[str, int] = Field(..., description="Identifier for the fuel type")  # Can be str (UUID) or int (DB ID)
    is_available_in_network: bool = Field(
        True, description="Indicates if this cab and fuel type combination is available for network trips"
    )

    class Config:
        from_orm = True
        from_attributes = True
        extra = "allow"


# Outstation-specific pricing schema
class OutstationCabPricingSchema(CabPricingBaseSchema):
    base_fare_per_km: float
    driver_allowance_per_day: float
    min_included_km_per_day: int
    overage_amount_per_km: float
    state_id: Optional[Union[str, int]] = None  # FK to State.id

    # Outstation-specific: daily allotted km, permit fee, etc. can be added here

    class Config:
        from_orm = True
        from_attributes = True
        extra = "allow"


# Local-specific pricing schema
class LocalCabPricingSchema(CabPricingBaseSchema):
    hourly_rate: float
    overage_amount_per_hour: float
    overage_amount_per_km: Optional[float] = None  # Optional for local trips
    region_id: Optional[Union[str, int]] = None  # FK to Region.id

    # Local-specific: minimum rental duration, etc. can be added here
    class Config:
        from_orm = True
        from_attributes = True
        extra = "allow"


# Airport-specific pricing schema
class AirportCabPricingSchema(CabPricingBaseSchema):
    cab_type_id: Optional[str]
    fuel_type_id: Optional[str]
    fare_per_km: float
    overage_amount_per_km: float
    region_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"


class PricingBreakdownBaseSchema(BaseModel):
    base_fare: float
    platform_fee: float

    class Config:
        from_attributes = True
        exclude_none = True  # Exclude fields with None values from the model dump


class OutstationPricingBreakdownSchema(PricingBreakdownBaseSchema):
    driver_allowance: Optional[float] = None
    minimum_toll_wallet: Optional[float] = None
    minimum_parking_wallet: Optional[float] = None
    permit_fee: Optional[float] = None
    quoted_price: Optional[float] = None  # Customer's counter-quote

    class Config:
        extra = "allow"


class LocalPricingBreakdownSchema(PricingBreakdownBaseSchema):
    driver_allowance: Optional[float] = None
    minimum_parking_wallet: Optional[float] = None
    quoted_price: Optional[float] = None  # Customer's counter-quote

    class Config:
        extra = "allow"


class AirportPricingBreakdownSchema(PricingBreakdownBaseSchema):
    placard_charge: Optional[float] = (
        None  # Only for airport pickup, can be null for others
    )
    toll: Optional[float] = None
    parking: Optional[float] = None
    quoted_price: Optional[float] = None  # Customer's counter-quote

    class Config:
        extra = "allow"


class OveragesSchema(BaseModel):
    indicative_overage_warning: Optional[bool] = False  # Add this field for UI
    overage_amount_per_km: Optional[float] = None  # For outstation trips
    overage_estimate_amount: Optional[float] = None  # For outstation trips
    overage_amount_per_hour: Optional[float] = None  # For local trips

    class Config:
        extra = "allow"
        exclude_none = True  # Exclude fields with None values from the model dump


class NightPricingConfigurationSchema(BaseModel):
    id: Optional[str]=None
    night_hours_label: Optional[str] = None  # e.g., "10 PM - 6 AM"
    night_overage_amount_per_block: Optional[float] = (
        None  # Amount charged for night trips
    )
    night_block_hours: Optional[int] = None  # Number of hours in a night block
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None
    region_id: Optional[str] = None  # FK to GeoRegion.id
    state_id: Optional[str] = None  # FK to State.id

    class Config:
        from_attributes = True
        extra = "allow"


class CommonPricingConfigurationSchema(BaseModel):
    id: Optional[str]= None
    trip_type_id: Optional[str] = None  # FK to TripType.id
    dynamic_platform_fee_percent: Optional[float] = None  # e.g., 5.0 for 5%
    min_included_hours: Optional[int] = None  # Local cab minimum included hours
    max_included_hours: Optional[int] = None  # Local cab maximum included hours
    min_included_km: Optional[int] = None  # For local cab minimum included km
    max_included_km: Optional[int] = None  # For local cab maximum included
    placard_charge: Optional[float] = (
        None  # Only for airport pickup, can be null for others
    )
    max_included_km: Optional[int] = None  # For airport pickup/drop
    overage_warning_km_threshold: Optional[float] = (
        None  # For airport pickup/drop and outstation
    )
    toll: Optional[float] = None  # For airport pickup and drop
    parking: Optional[float] = None  # For airport pickup
    state_id: Optional[str] = None  # FK to State.id
    region_id: Optional[str] = None  # FK to GeoRegion.id
    minimum_toll_wallet: Optional[float] = None  # For local/outstation
    minimum_parking_wallet: Optional[float] = None  # For local/outstation
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"


# Permit fee configuration schema is used to define permit fees state wise for outstation trips
class PermitFeeConfigurationSchema(BaseModel):
    id: Optional[str]= None
    state_id: str  # FK to State.id
    cab_type_id: str  # FK to CabType.id
    fuel_type_id: str  # FK to FuelType.id
    permit_fee: float  # Permit fee amount
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"


# Fixed platform fee configuration schema is used to define fixed platform fee per booking irrespective of cab type, fuel type, trip type, region, state etc.
class FixedPlatformFeeConfigurationSchema(BaseModel):
    id: Optional[str]
    fixed_platform_fee: float = Field(0.0, description="Fixed platform fee per booking")  # e.g., 50.0 for ₹50
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"
        from_orm = True

class AuxiliaryPricingConfiguration(BaseModel):
    common: Optional[CommonPricingConfigurationSchema] = None
    night: Optional[NightPricingConfigurationSchema] = None # Includes region wise and state wise night pricing configurations for outstation and local
    permit: Optional[PermitFeeConfigurationSchema] = None # Includes permit fee configurations state wise for outstation trips

class MasterPricingConfiguration(BaseModel):
    base_pricing: List[
        tuple[
            Union[
                OutstationCabPricingSchema,
                AirportCabPricingSchema,
                LocalCabPricingSchema,
            ],
            CabTypeSchema,
            FuelTypeSchema,
        ]
    ] = []
    auxiliary_pricing: AuxiliaryPricingConfiguration = Field(default_factory=AuxiliaryPricingConfiguration)

     

    class Config:
        from_attributes = True
        extra = "allow"