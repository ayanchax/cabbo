from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, Optional, List, Union
from datetime import datetime
from core.exceptions import CabboException
from models.customer.customer_schema import CustomerRead
from models.policies.dispute_schema import InitialDisputeSchema
from models.pricing.pricing_schema import (
    AirportPricingBreakdownSchema,
    ExtraPayments,
    LocalPricingBreakdownSchema,
    OutstationPricingBreakdownSchema,
    OveragesSchema,
    TripPackageConfigSchema,
)
from models.customer.passenger_schema import PassengerRequest
from models.financial.payments_schema import RazorPayPaymentResponse
from models.trip.trip_enums import (
    TripStatusEnum,
    TripTypeEnum,
    FuelTypeEnum,
    CarTypeEnum,
    CancellationSubStatusEnum,
)
from models.map.location_schema import LocationInfo
from models.pricing.pricing_orm import RoleEnum

class TripTypeSchema(BaseModel):
    id: Optional[str]
    trip_type: TripTypeEnum
    display_name: str
    description: Optional[str]

    class Config:
        from_attributes = True
        extra = "allow"

class TripTypeUpdateSchema(BaseModel):
    id:Optional[str]=None
    trip_type: Optional[TripTypeEnum] = None
    display_name: Optional[str] = None
    description: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "allow"

class TripDetails(BaseModel):
    # Trip type and package
    trip_type: Optional[TripTypeEnum] = None
    package_id: Optional[str] = None
    package_label: Optional[str] = None
    package_label_short: Optional[str] = None

    # Location info
    origin: Optional[LocationInfo] = None
    destination: Optional[LocationInfo] = None
    hops: Optional[List[LocationInfo]] = None
    is_interstate: Optional[bool] = None
    total_unique_states: Optional[int] = None
    unique_states: Optional[List[str]] = None
    is_round_trip: Optional[bool] = None

    # Date and time
    start_datetime: Optional[datetime] = None
    expected_end_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    total_days: Optional[int] = None

    # Passenger and luggage
    num_adults: Optional[int] = None
    num_children: Optional[int] = None
    num_passengers: Optional[int] = None
    num_large_suitcases: Optional[int] = None
    num_carryons: Optional[int] = None
    num_backpacks: Optional[int] = None
    num_other_bags: Optional[int] = None
    num_luggages: Optional[int] = None

    # Car and fuel preferences
    preferred_car_type: Optional[CarTypeEnum] = None
    preferred_fuel_type: Optional[FuelTypeEnum] = None
    in_car_amenities: Optional[dict] = None

    # Financials
    base_fare: Optional[float] = None
    driver_allowance: Optional[float] = None
    tolls: Optional[float] = None
    parking: Optional[float] = None
    permit_fee: Optional[float] = None
    platform_fee: Optional[float] = None
    final_price: Optional[float] = None
    final_display_price: Optional[float] = None
    advance_payment: Optional[float] = None
    balance_payment: Optional[float] = None
    price_breakdown: Optional[dict] = None
    overages: Optional[dict] = None

    # Inclusions and exclusions
    inclusions: Optional[List[str]] = None
    exclusions: Optional[List[str]] = None

    # Airport/flight metadata
    flight_number: Optional[str] = None
    terminal_number: Optional[str] = None
    toll_road_preferred: Optional[bool] = None
    placard_required: Optional[bool] = None
    placard_name: Optional[str] = None

    # Metadata
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    estimated_km: Optional[float] = None
    indicative_overage_warning: Optional[bool] = None
    alternate_customer_phone: Optional[str] = None
    passenger: Optional[PassengerRequest] = None  # Passenger details
 

    class Config:
        from_attributes = True
        extra = "allow"  # Allow extra fields not defined in the model
        exclude_none = True  # Exclude fields with None values from the model dump

class TripCreate(BaseModel):
    trip_id: str  # Unique trip ID for the trip for internal use
    booking_id: Optional[str] = None  # Unique booking ID for the trip which will be different from trip_id and generally used for customer communication
    payment_info: Optional[RazorPayPaymentResponse]  # Payment details is mandatory
    status: TripStatusEnum = TripStatusEnum.pending  # Initial status of the trip
    trip_details:TripDetails
 
class TripOut(BaseModel):
    trip_id: str  # Unique trip ID for the trip for internal use
    payment_info: RazorPayPaymentResponse  # Payment details is mandatory as we do not confirm trips without an advance payment
    
    class Config:
        from_attributes = True

class TripStatusAuditOut(BaseModel):
    id: int
    trip_id: str
    booking_id: str
    status: TripStatusEnum
    changed_by: str
    reason: Optional[str] = None
    timestamp: datetime
    cancellation_sub_status: Optional[CancellationSubStatusEnum] = None
    

    class Config:
        from_attributes = True


class TripTypeMasterOut(BaseModel):
    id: str
    booking_id: str
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
        None  # Available for outstation and hourly rental multi-hop trips [Providing hops by customer helps us approximate the overages more efficiently and helps the customer get almost accurate rates upfront]
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
    included_kms: Optional[float] = None
    included_hours: Optional[int] = None  # For local trips
    package_short_label: Optional[str] = (
        None  # Short label for the package, e.g., "4 Hours / 40 KM"
    )
    package: Optional[Union[TripPackageConfigSchema, str]] = None  # For local trips
    overages: Optional[OveragesSchema] = None

    class Config:
        extra = "allow"  # Allow extra fields not defined in the model
        exclude_none = True  # Exclude fields with None values from the model dump
    
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

    included_hours: Optional[float] = None  # Included hours for the trip, mainly applicable for local trips

    included_kms: Optional[float] = None  # Included kilometers for the trip, mainly applicable for outstation and local trips
    choices:Optional[int] = None  # Number of choices available for the user to book from
    
    is_interstate: Optional[bool] = (
        False  # Indicates if the trip is interstate, mainly applicable for outstation trips
    )  # This is used to calculate the total price for outstation trips which are interstate
    total_unique_states: Optional[int] = (
        None  # Applicable for outstation trips which are interstate
    )
    unique_states: Optional[List[str]] = (
        None  # Comma-separated list of unique states, applicable for outstation trips which are interstate
    )

    is_round_trip: Optional[bool] = (
        False  # Indicates if the trip is a round trip, mainly applicable for outstation trips and local trips
    )  # This is used to calculate the total price for outstation trips which are round trips


    class Config:
        extra = "forbid"  # Allow extra fields not defined in the model
        exclude_none = True
    
class TripSearchResponse(BaseModel):
    options: List[TripSearchOption]
    preferences: Optional[TripSearchRequest] = None  # User preferences used for search
    metadata:Optional[Union[dict,TripSearchAdditionalData]] = None  # Metadata about the trip search, like total options found, etc.

class TripBookRequest(BaseModel):
    option: TripSearchOption  # Selected option to book
    preferences: TripSearchRequest
    metadata: Optional[TripSearchAdditionalData] = None  # Additional metadata for the booking




class TripDetailSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the trip")
    booking_id: Optional[str] = Field(None, description="Unique booking reference ID")
    
    # Creator information
    customer:Optional[CustomerRead] = Field(None, description="Customer details of the trip creator, included only if the creator is a customer and if the requesting user has permission to view customer details")
    # Trip details
    trip_type: Optional[TripTypeSchema] = Field(None, description="Trip type details")
    
    # Location information
    origin: Optional[LocationInfo] = Field(None, description="Origin city details")
    destination: Optional[LocationInfo] = Field(None, description="Destination city details")
    hops: Optional[List[LocationInfo]] = Field(None, description="List of hops for the trip")
    is_interstate: Optional[bool] = Field(None, description="Indicates if the trip is interstate")
    total_unique_states: Optional[int] = Field(None, description="Total unique states for interstate trips")
    unique_states: Optional[List[str]] = Field(None, description="List of unique states for interstate trips")
    is_round_trip: Optional[bool] = Field(None, description="Indicates if the trip is a round trip")

    # Package information
    package_label: Optional[str] = Field(None, description="Label for the package (e.g., '4 Hours / 40 KM')")
    package_label_short: Optional[str] = Field(None, description="Short label for the package (e.g., '4H/40KM')")
    package: Optional[Union[TripPackageConfigSchema, str]] = Field(None, description="Package details for local trips")
    # Date and time information
    start_datetime: Optional[datetime] = Field(None, description="Start date and time of the trip")
    expected_end_datetime: Optional[datetime] = Field(None, description="Expected end date and time of the trip")
    end_datetime: Optional[datetime] = Field(None, description="Actual end date and time of the trip")
    cancelation_datetime: Optional[datetime] = Field(None, description="Cancellation date and time of the trip, if applicable")
    total_days: Optional[int] = Field(None, description="Total days for outstation trips")
    included_kms: Optional[float] = Field(None, description="Included kilometers for the trip")

    # Passenger and luggage information
    num_adults: Optional[int] = Field(None, description="Number of adults")
    num_children: Optional[int] = Field(None, description="Number of children")
    num_large_suitcases: Optional[int] = Field(None, description="Number of large suitcases")
    num_carryons: Optional[int] = Field(None, description="Number of carry-on bags")
    num_backpacks: Optional[int] = Field(None, description="Number of backpacks")
    num_other_bags: Optional[int] = Field(None, description="Number of other bags")
    num_luggages: Optional[int] = Field(None, description="Total luggage count")
    num_passengers: Optional[int] = Field(None, description="Total number of passengers")

    # Car and fuel preferences
    preferred_car_type: Optional[CarTypeEnum] = Field(None, description="Preferred car type")
    preferred_fuel_type: Optional[FuelTypeEnum] = Field(None, description="Preferred fuel type")
    in_car_amenities: Optional[AmenitiesSchema] = Field(None, description="Dictionary of in-car amenities")

    # Driver assignment fields
    driver: Optional[Union[Dict[str, Any], Any]] = Field(None, description="Driver details of the assigned driver")
    
    # Trip status
    status: Optional[TripStatusEnum] = Field(None, description="Current status of the trip")

    # Financial fields
    base_fare: Optional[float] = Field(None, description="Base fare for the trip")
    driver_allowance: Optional[float] = Field(None, description="Driver allowance for outstation trips")
    tolls: Optional[float] = Field(None, description="Toll charges for the trip")
    parking: Optional[float] = Field(None, description="Parking charges for the trip")
    permit_fee: Optional[float] = Field(None, description="Interstate permit fee for outstation trips")
    platform_fee: Optional[float] = Field(None, description="Platform fee charged by the system")
    final_price: Optional[float] = Field(None, description="Final price calculated for the trip")
    final_display_price: Optional[float] = Field(None, description="Final price shown to the driver admin")
    advance_payment: Optional[float] = Field(None, description="Advance payment made by the customer")
    balance_payment: Optional[float] = Field(None, description="Balance payment to be made by the customer")
    payment_provider_metadata: Optional[Dict] = Field(None, description="Payment details (e.g., mode, transaction ID)")
    price_breakdown: Optional[Dict] = Field(None, description="Detailed price breakdown")
    overages: Optional[Dict] = Field(None, description="Details of overages (e.g., extra km charges)")
    refund_id: Optional[str] = Field(None, description="Refund transaction ID from payment provider, if any")

    # Inclusions and exclusions
    inclusions: Optional[List[str]] = Field(None, description="List of inclusions for the trip")
    exclusions: Optional[List[str]] = Field(None, description="List of exclusions for the trip")

    # Airport pickup/flight metadata
    flight_number: Optional[str] = Field(None, description="Flight number for airport trips")
    terminal_number: Optional[str] = Field(None, description="Terminal number for airport trips")
    toll_road_preferred: Optional[bool] = Field(None, description="Indicates if toll roads are preferred")
    placard_required: Optional[bool] = Field(None, description="Indicates if a placard is required")
    placard_name: Optional[str] = Field(None, description="Name to be displayed on the placard")

    # Additional metadata
    special_needs_requests: Optional[str] = Field(None, description="Special needs or requests from the customer")
    estimated_km: Optional[float] = Field(None, description="Estimated distance for the trip")
    indicative_overage_warning: Optional[bool] = Field(None, description="Indicates if overage warnings are applicable")
    alternate_customer_phone: Optional[str] = Field(None, description="Alternate phone number for the customer")
    
    passenger: Optional[PassengerRequest] = Field(None, description="Passenger details if the trip is booked for someone else")
    # Metadata
    created_at: Optional[datetime] = Field(None, description="Timestamp when the trip was created")
    updated_at: Optional[datetime] = Field(None, description="Timestamp when the trip was last updated")

    class Config:
        from_attributes = True
        extra = "allow"  # Allow extra fields not defined in the model
        exclude_none = True  # Exclude fields with None values from the model dump


class AdditionalDetailsOnTripStatusChange(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for the status change, especially important for cancellations")
    cancellation_sub_status: Optional[CancellationSubStatusEnum] = Field(None, description="Sub-status for cancellations to provide more context on the cancellation reason")
    dispute_detail:Optional[InitialDisputeSchema] = Field(None, description="Details of the dispute to be created when the trip status is changed to dispute")
    extra_payment_to_driver: Optional[ExtraPayments] = Field(None, description="Details of any extra payment to driver at trip completion, such as tolls paid by driver, parking charges, overage payment for extra distance or time, tips from customer, etc.")
    start_datetime: Optional[datetime] = Field(None, description="Actual start date and time of the trip, useful for calculating any overages in case of outstation and local trips")
    end_datetime: Optional[datetime] = Field(None, description="Actual end date and time of the trip, useful for calculating any overages in case of outstation and local trips")
    class Config:
        extra = "forbid"  # Forbid extra fields not defined in the model
        exclude_none = True  # Exclude fields with None values from the model dump