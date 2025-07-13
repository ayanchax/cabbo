from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Union


# Base schema for common trip pricing fields
class CabPricingBaseSchema(BaseModel):
    id: Optional[Union[int, str]]
    cab_type_id: Union[str, int]  # Can be str (UUID) or int (DB ID)
    fuel_type_id: Union[str, int]  # Can be str (UUID) or int (DB ID)
    is_available_in_network: bool = True  # Indicates if this cab type is available in the network

    class Config:
        from_attributes = True
        extra = "allow"


# Outstation-specific pricing schema
class OutstationCabPricingSchema(CabPricingBaseSchema):
    base_fare_per_km: float
    driver_allowance_per_day: float
    min_included_km_per_day: int
    overage_amount_per_km: float

    # Outstation-specific: daily allotted km, permit fee, etc. can be added here


# Local-specific pricing schema
class LocalCabPricingSchema(CabPricingBaseSchema):
    hourly_rate: float
    overage_amount_per_hour: float
    overage_amount_per_km: Optional[float] = None  # Optional for local trips

    # Local-specific: minimum rental duration, etc. can be added here


# Airport-specific pricing schema
class AirportCabPricingSchema(CabPricingBaseSchema):
    id: Optional[str]
    cab_type_id: Optional[str]
    fuel_type_id: Optional[str]
    airport_fare_per_km: float
    overage_amount_per_km: float
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None


class CabTypeSchema(BaseModel):
    id: Optional[str]
    name: str
    capacity:Optional[str] = None  # e.g., "4+1", "6+1"

    class Config:
        from_attributes = True


class FuelTypeSchema(BaseModel):
    id: Optional[str]
    name: str

    class Config:
        from_attributes = True


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


class FixedNightPricingSchema(BaseModel):
    id: Optional[str]
    night_hours_label: Optional[str] = None  # e.g., "10 PM - 6 AM"
    night_overage_amount_per_block: Optional[float] = (
        None  # Amount charged for night trips
    )
    night_block_hours: Optional[int] = None  # Number of hours in a night block
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"


class CommonPricingConfigSchema(BaseModel):
    id: Optional[str]
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
    minimum_toll_wallet: Optional[float] = None  # For local/outstation
    minimum_parking_wallet: Optional[float] = None  # For local/outstation
    fixed_platform_fee: Optional[float] = None  # e.g., 50.0 for ₹50
    fixed_night_pricing: Optional[FixedNightPricingSchema] = (
        None  # Fixed night pricing details for mainly outstation trips
    )
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"


class PermitFeeSchema(BaseModel):
    id: Optional[str]
    state_id: str  # FK to GeoState.id
    cab_type_id: str  # FK to CabType.id
    fuel_type_id: str  # FK to FuelType.id
    permit_fee: float  # Permit fee amount
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"
