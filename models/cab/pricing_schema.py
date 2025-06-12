from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from models.trip.trip_enums import TripTypeEnum


# Base schema for common trip pricing fields
class CabPricingBaseSchema(BaseModel):
    id: Optional[int]
    cab_type_id: int
    fuel_type_id: int

    class Config:
        from_attributes = True


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
    overage_per_hour: float
    overage_per_km: Optional[float] = None  # Optional for local trips
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

    class Config:

        from_attributes = True


class CabTypeSchema(BaseModel):
    id: Optional[str]
    name: str

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


class OutstationPricingBreakdownSchema(PricingBreakdownBaseSchema):
    driver_allowance: Optional[float] = None
    minimum_toll: Optional[float] = None
    minimum_parking: Optional[float] = None
    permit_fee: Optional[float] = None
    quoted_price: Optional[float] = None  # Customer's counter-quote

    class Config:
        extra = "allow"


class LocalPricingBreakdownSchema(PricingBreakdownBaseSchema):
    driver_allowance: Optional[float] = None
    minimum_toll: Optional[float] = None
    minimum_parking: Optional[float] = None
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
    overage_estimate: Optional[float] = None  # For outstation trips
    overage_amount_per_hour: Optional[float] = None  # For local trips

    class Config:
        extra = "allow"


class CommonPricingConfigSchema(BaseModel):
    id: Optional[str]
    trip_type_id: TripTypeEnum
    dynamic_platform_fee_percent: float  # e.g., 5.0 for 5%
    min_included_hours: Optional[int] = None  # Local cab minimum included hours
    max_included_hours: Optional[int] = None  # Local cab maximum included hours
    placard_charge: Optional[float] = (
        None  # Only for airport pickup, can be null for others
    )
    max_included_km: Optional[int] = None  # For airport pickup/drop
    overage_warning_km_threshold: Optional[float] = (
        None  # For airport pickup/drop and outstation
    )
    toll: Optional[float] = None  # For airport pickup and drop
    parking: Optional[float] = None  # For airport pickup
    minimum_toll: Optional[float] = None  # For local/outstation
    minimum_parking: Optional[float] = None  # For local/outstation
    fixed_platform_fee: Optional[float] = None  # e.g., 50.0 for ₹50
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
        extra = "allow"
