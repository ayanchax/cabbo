from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from models.trip.trip_enums import TripStatusEnum, TripTypeEnum


class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None


class TripBase(BaseModel):
    trip_type: TripTypeEnum
    origin: LocationInfo
    destination: LocationInfo
    start_date: datetime
    end_date: datetime
    num_passengers: int
    luggage_info: Optional[str] = None
    preferred_car_type: Optional[str] = None


class TripCreate(TripBase):
    pass


class TripOut(TripBase):
    id: int
    user_id: int
    status: TripStatusEnum
    base_fare: Optional[float]
    driver_allowance: Optional[float]
    tolls_estimate: Optional[float]
    parking_estimate: Optional[float]
    platform_fee: Optional[float]
    quoted_price: Optional[float]
    final_price: Optional[float]
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class TripStatusAuditOut(BaseModel):
    id: int
    trip_id: int
    status: TripStatusEnum
    changed_by: str
    timestamp: datetime

    class Config:
        orm_mode = True
