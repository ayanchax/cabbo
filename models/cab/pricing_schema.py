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
    overage_per_km: float
    night_overage_per_block: float
    night_block_hours: int
    # Outstation-specific: daily allotted km, permit fee, etc. can be added here


# Local-specific pricing schema
class LocalCabPricingSchema(CabPricingBaseSchema):
    hourly_rate: float
    min_included_hours: int
    max_included_hours: int
    overage_per_hour: float
    # Local-specific: minimum rental duration, etc. can be added here


# Airport-specific pricing schema
class AirportCabPricingSchema(CabPricingBaseSchema):
    id: Optional[str]
    cab_type_id: Optional[str]
    fuel_type_id: Optional[str]
    airport_fare_per_km: float
    placard_charge: Optional[float] = None
    max_included_km: int
    overage_per_km: float
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


class TollParkingConfigSchema(BaseModel):
    id: Optional[str]
    trip_type: TripTypeEnum
    toll: Optional[float]
    parking: Optional[float]
    toll_per_block: Optional[float]
    parking_per_block: Optional[float]
    block_days: Optional[int]
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True


class PricingBreakdownBaseSchema(BaseModel):
    base_fare: float
    platform_fee: float

    class Config:
        from_attributes = True


class OutstationPricingBreakdownSchema(PricingBreakdownBaseSchema):
    driver_allowance: Optional[float] = None
    tolls_estimate: Optional[float] = None
    parking_estimate: Optional[float] = None
    permit_fee: Optional[float] = None
    quoted_price: Optional[float] = None  # Customer's counter-quote

    class Config:
        extra = "allow"


class LocalPricingBreakdownSchema(PricingBreakdownBaseSchema):
    driver_allowance: Optional[float] = None
    tolls_estimate: Optional[float] = None
    parking_estimate: Optional[float] = None
    quoted_price: Optional[float] = None  # Customer's counter-quote

    class Config:
        extra = "allow"


class AirportPricingBreakdownSchema(PricingBreakdownBaseSchema):
    placard_charge: Optional[float] = (
        None  # Only for airport pickup, can be null for others
    )
    tolls_estimate: Optional[float] = None
    parking_estimate: Optional[float] = None
    quoted_price: Optional[float] = None  # Customer's counter-quote

    class Config:
        extra = "allow"


class OverageWarningConfigSchema(BaseModel):
    id: Optional[str]
    trip_type: TripTypeEnum
    warning_km_threshold: float
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True


class PlatformPricingConfigSchema(BaseModel):
    id: Optional[str]
    trip_type_id: str
    platform_fee_percent: float
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    last_modified: Optional[datetime] = None

    class Config:
        from_attributes = True
