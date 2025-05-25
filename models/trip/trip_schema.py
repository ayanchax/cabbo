from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from models.trip.trip_enums import (
    TripStatusEnum,
    TripTypeEnum,
    FuelTypeEnum,
    CarTypeEnum,
)
from models.geography.geo_enums import LocationInfo


class TripBase(BaseModel):
    trip_type: TripTypeEnum
    origin: LocationInfo
    destination: LocationInfo
    start_date: datetime
    end_date: datetime
    num_adults: int
    num_children: int
    num_large_suitcases: Optional[int] = None
    num_carryons: Optional[int] = None
    num_backpacks: Optional[int] = None
    num_other_bags: Optional[int] = None
    preferred_car_type: Optional[CarTypeEnum] = CarTypeEnum.sedan
    preferred_fuel_type: Optional[FuelTypeEnum] = FuelTypeEnum.diesel
    hops: Optional[List[str]] = None  # For outstation multi-hop
    is_round_trip: Optional[bool] = True
    is_interstate: Optional[bool] = False
    permit_fee: Optional[float] = None
    # Driver assignment fields
    driver_name: Optional[str] = None
    driver_phone: Optional[str] = None
    car_model: Optional[str] = None
    car_registration_number: Optional[str] = None
    payment_mode: Optional[str] = None
    payment_number: Optional[str] = None
    flight_number: Optional[str] = None
    terminal_number: Optional[str] = None
    final_display_price: Optional[float] = (
        None  # Price shown to driver admin (original or quoted)
    )

    # num_luggages is now computed as the sum of all above fields
    @property
    def num_luggages(self) -> int:
        return sum(
            filter(
                None,
                [
                    self.num_large_suitcases,
                    self.num_carryons,
                    self.num_backpacks,
                    self.num_other_bags,
                ],
            )
        )


class TripCreate(TripBase):
    pass


class TripOut(TripBase):
    id: str
    creator_id: str
    creator_type: str
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
    trip_id: str
    status: TripStatusEnum
    changed_by: str
    reason: Optional[str] = None
    timestamp: datetime

    class Config:
        orm_mode = True


class OutstandingDueOut(BaseModel):
    id: int
    trip_id: str
    customer_id: str
    amount: float
    reason: str
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True
