from pydantic import BaseModel, field_validator
from typing import Optional, List, Union
from datetime import datetime
from core.exceptions import CabboException
from models.cab.pricing_schema import (
    AirportPricingBreakdownSchema,
    LocalPricingBreakdownSchema,
    OutstationPricingBreakdownSchema,
    OveragesSchema,
)
from models.customer.passenger_schema import PassengerOut, PassengerRequest
from models.trip.trip_enums import (
    TripStatusEnum,
    TripTypeEnum,
    FuelTypeEnum,
    CarTypeEnum,
    CancellationSubStatusEnum,
)
from models.geography.geo_enums import LocationInfo
from models.cab.pricing_orm import RoleEnum
from utils.utility import validate_and_sanitize_country_phone


class TripBase(BaseModel):
    trip_type: TripTypeEnum
    origin: LocationInfo
    destination: LocationInfo
    start_date: datetime
    end_date: datetime
    num_adults: int
    num_children: int
    num_large_suitcases: Optional[int] = None  # Trolley bags, large suitcases
    num_carryons: Optional[int] = None
    num_backpacks: Optional[int] = None
    num_other_bags: Optional[int] = None
    preferred_car_type: Optional[CarTypeEnum] = CarTypeEnum.sedan
    preferred_fuel_type: Optional[FuelTypeEnum] = FuelTypeEnum.diesel
    hops: Optional[List[str]] = None  # For outstation multi-hop
    is_round_trip: Optional[bool] = True
    is_interstate: Optional[bool] = False
    total_unique_states: Optional[int] = (
        None  # Applicable for outstation trips which are interstate
    )
    unique_states: Optional[str] = (
        None  # Comma-separated list of unique states, applicable for outstation trips which are interstate
    )
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
    placard_required: Optional[bool] = False
    placard_name: Optional[str] = None
    # If customer wants to provide an alternate phone number for contacting during the trip.
    # This is optional and can be used for special cases like airport pickups
    # where the customer may not be reachable on their primary number.
    # However all invoices and receipts will still go to the primary phone number.
    alternate_customer_phone: Optional[str] = None

    # Optional: passenger info for 'book for someone else' feature
    passenger: Optional[Union[str, PassengerRequest]] = None # If provided, trip is for someone else
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
    @property
    def num_passengers(self) -> int:
        return self.num_adults + self.num_children

    @field_validator("alternate_customer_phone", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        v = v.strip()
        if v == "":
            return v
        return validate_and_sanitize_country_phone(v)


class TripCreate(TripBase):
    pass


class TripOut(TripBase):
    id: str
    creator_id: str
    creator_type: RoleEnum = RoleEnum.customer
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
    passenger_id: Optional[str] = None  # FK to passengers.id if not self

    class Config:
        from_attributes = True


class TripStatusAuditOut(BaseModel):
    id: int
    trip_id: str
    status: TripStatusEnum
    changed_by: str
    reason: Optional[str] = None
    timestamp: datetime
    cancellation_sub_status: Optional[CancellationSubStatusEnum] = None
    # Nullable: Only populated when cancellation_sub_status == CancellationSubStatusEnum.customer_preferences_not_met
    responsible_preference_keys_for_cancelation: Optional[str] = (
        None  # Comma-separated or JSON string of unmet preferences
    )

    class Config:
        from_attributes = True


class OutstandingDueOut(BaseModel):
    id: int
    trip_id: str
    customer_id: str
    amount: float
    reason: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TripTypeMasterOut(BaseModel):
    id: str
    trip_type: TripTypeEnum
    display_name: str
    description: Optional[str]
    created_by: RoleEnum
    created_at: datetime
    last_modified: datetime

    class Config:
        from_attributes = True


class TripSearchRequest(BaseModel):
    trip_type: TripTypeEnum
    origin: Optional[LocationInfo] = None  # For airport trips, this is the pickup location
    hops: Optional[Union[List[str], List[LocationInfo]]] = (
        None  # Available for outstation and hourly rental multi-hop trips [Providing hops by customer helps us approximate the overages more efficiently and helps the customer get almost accurate quotes upfront]
    )
    destination: Optional[LocationInfo] = None
    start_date: str  # ISO date or datetime string
    end_date: Optional[str] = None
    expected_end_date: Optional[str] = (
        None  # for local trips, we set it by package chosen
    )
    num_adults: int
    num_children: int
    num_large_suitcases: Optional[int] = 0  # Trolley bags, large suitcases
    num_carryons: Optional[int] = 0
    num_backpacks: Optional[int] = 0
    num_other_bags: Optional[int] = 0
    preferred_car_type: Optional[CarTypeEnum] = CarTypeEnum.sedan
    preferred_fuel_type: Optional[FuelTypeEnum] = FuelTypeEnum.diesel
    package_id: Optional[str] = None  # For local trips
    flight_number: Optional[str] = None  # For airport pickup
    terminal_number: Optional[str] = None  # For airport pickup
    toll_road_preferred: Optional[bool] = (
        False  # For airport trips Indicates if toll roads are preferred
    )
    placard_required: Optional[bool] = (
        False  # For airport pickup Indicates if a placard is needed
    )
    placard_name: Optional[str] = (
        None  # Name to display on the placard for airport pickup
    )
    passenger: Optional[Union[str, PassengerRequest]] = None

    # Validate trip type and ensure it is one of the supported types
    @field_validator("trip_type", mode="before")
    @classmethod
    def validate_trip_type(cls, v):
        valid_trip_types = [
            TripTypeEnum.airport_pickup,
            TripTypeEnum.airport_drop,
            TripTypeEnum.local,
            TripTypeEnum.outstation,
        ]
        if v not in valid_trip_types:
            supported_types = ", ".join([t.value for t in valid_trip_types])
            raise CabboException(
                f"Invalid trip type. Supported types are: {supported_types}",
                status_code=400,
            )
        return v


class TripPackageConfigSchema(BaseModel):
    id: Optional[str] = None  # Optional ID for existing packages
    trip_type_id: Optional[str] = None  # FK to TripTypeMaster.id
    included_hours: int  # e.g., 4, 6, 8, 10, 12
    included_km: int  # e.g., 40, 60, 80, 100, 120
    package_label: str  # e.g., "4 Hours / 40 KM", "6 Hours / 60 KM"
    driver_allowance: Optional[float] = (
        None  # Optional driver allowance for the package, this will apply for trip packages where duration of ride>=12hrs
    )

    class Config:
        from_attributes = True


class AmenitiesSchema(BaseModel):
    ac: bool = True  # Air conditioning
    music_system: bool = True  # Music system
    water_bottle: bool = False  # Water bottle
    tissues: bool = False  # Tissues
    candies: bool = False  # Candies
    snacks: bool = False  # Snacks
    phone_charger: bool = False  # Phone charger
    aux_cable: bool = False  # Aux cable for music
    bluetooth: bool = False  # Bluetooth connectivity
    wifi: bool = False  # Wifi connectivity


class TripSearchOption(BaseModel):
    car_type: CarTypeEnum
    fuel_type: FuelTypeEnum
    total_price: float
    price_breakdown: Union[
        AirportPricingBreakdownSchema,
        OutstationPricingBreakdownSchema,
        LocalPricingBreakdownSchema,
    ]  # Trip type specific pricing breakdown
    included_km: Optional[float] = None
    included_hours: Optional[int] = None  # For local trips
    package_short_label: Optional[str] = (
        None  # Short label for the package, e.g., "4 Hours / 40 KM"
    )
    package: Optional[Union[TripPackageConfigSchema, str]] = None  # For local trips
    overages: Optional[OveragesSchema] = None

    class Config:
        extra = "allow"  # Allow extra fields not defined in the model
    
class TripSearchAdditionalData(BaseModel):
    inclusions: Optional[List[str]] = (
        None  # List of inclusions like tolls, parking, etc.
    )
    exclusions: Optional[List[str]] = (
        None  # List of exclusions like fuel, driver meals, etc.
    )
    in_car_amenities: Optional[AmenitiesSchema] = (
        None  # List of in-car amenities like water bottles, tissues, etc.
    )
    total_trip_days: Optional[int] = (
        None  # Total number of days for the trip, mainly applicable for outstation trips  # This is used to calculate the total price for outstation trips which are multi-day trips
    )
    estimated_km: Optional[float] = (
        None  # Estimated kilometers for the trip, mainly applicable for outstation trips  # This is used to calculate the total price for outstation trips which are multi-day trips
    )
    choices:Optional[int] = None  # Number of choices available for the user to book from
    
    is_interstate: Optional[bool] = (
        None  # Indicates if the trip is interstate, mainly applicable for outstation trips
    )  # This is used to calculate the total price for outstation trips which are interstate
    total_unique_states: Optional[int] = (
        None  # Applicable for outstation trips which are interstate
    )
    unique_states: Optional[List[str]] = (
        None  # Comma-separated list of unique states, applicable for outstation trips which are interstate
    )

    is_round_trip: Optional[bool] = (
        True  # Indicates if the trip is a round trip, mainly applicable for outstation trips
    )  # This is used to calculate the total price for outstation trips which are round trips

    class Config:
        extra = "allow"  # Allow extra fields not defined in the model
    
class TripSearchResponse(BaseModel):
    options: List[TripSearchOption]
    preferences: Optional[TripSearchRequest] = None  # User preferences used for search
    metadata:Optional[TripSearchAdditionalData] = None  # Metadata about the trip search, like total options found, etc.

class TripBookRequest(BaseModel):
    option: TripSearchOption  # Selected option to book
    preferences: TripSearchRequest
    metadata: Optional[TripSearchAdditionalData] = None  # Additional metadata for the booking
