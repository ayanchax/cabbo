from pydantic import BaseModel
from typing import Optional
from models.trip.trip_enums import TripTypeEnum


# Base schema for common trip pricing fields
class CabPricingBaseSchema(BaseModel):
    id: Optional[int]
    cab_type_id: int
    fuel_type_id: int

    class Config:
        orm_mode = True


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
    airport_fare_per_km: float
    max_included_km: int
    overage_per_km: float
    # Airport-specific: any other fields can be added here


class CabTypeSchema(BaseModel):
    id: Optional[int]
    name: str

    class Config:
        orm_mode = True


class FuelTypeSchema(BaseModel):
    id: Optional[int]
    name: str

    class Config:
        orm_mode = True


class TollParkingConfigSchema(BaseModel):
    id: Optional[int]
    trip_type: TripTypeEnum
    toll: Optional[float]
    parking: Optional[float]
    toll_per_block: Optional[float]
    parking_per_block: Optional[float]
    block_days: Optional[int]

    class Config:
        orm_mode = True
