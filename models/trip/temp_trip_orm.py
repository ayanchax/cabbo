from core.security import RoleEnum
from models.trip.trip_enums import (
    FuelTypeEnum,
    CarTypeEnum,
)
import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import (
    JSON,
    Column,
    Integer,
    String,
    Enum,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    Text,
)
from sqlalchemy.sql import func
from db.database import Base
class TempTrip(Base):
    __tablename__ = "temp_trips"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    #  Creator information
    creator_id = Column(MySQL_CHAR(36), nullable=False, index=True)
    creator_type = Column(
        Enum(RoleEnum),  # Assuming RoleEnum includes customer, driver, admin
        default=RoleEnum.customer,
        nullable=False,
    )
    #  Creator information - END

    # Trip details
    trip_type_id = Column(
        MySQL_CHAR(36), nullable=False,
    )  # FK to trip types master table

    # Location information
    origin=Column(JSON, nullable=False)  # Origin city name
    destination=Column(JSON, nullable=False)  # Destination city name
    hops = Column(
        JSON, nullable=True
    )  # JSON/text list of hops for outstation and hourly rental [Providing hops by customer helps us approximate the overages more efficiently]
    is_interstate = Column(Boolean, default=False, nullable=False)
    total_unique_states = Column(
        Integer, nullable=True
    )  ##Applicable for outstation trips which are interstate
    unique_states = Column(
        JSON, nullable=True
    )  # comma separated list of unique states, applicable for outstation trips which are interstate
    is_round_trip = Column(Boolean, default=True, nullable=False)
    # Location information - END

    # Package information selected by customer
    # This is applicable only for hourly rental trips
    package_id = Column(
        MySQL_CHAR(36), nullable=True, index=True
    )  # FK to trip package config table for hourly rental trips
    package_label = Column(
        String(255), nullable=True, default=None
    )  # Label for the package, e.g., "4 Hours / 40 KM" 
    package_label_short = Column(
        String(100), nullable=True, default=None
    )  # Short label for the package, e.g., "4H/40KM" 
    # Package information selected by customer - END
    
    # Date and time information
    start_datetime = Column(DateTime, nullable=False)
    expected_end_datetime = Column(
        DateTime, nullable=True
    )  # Nullable | for local trips, we set it by package chosen
    end_datetime = Column(DateTime, nullable=True)
    total_days = Column(
        Integer, nullable=False, default=1
    )  # Total days for outstation trips
    # Date and time information - END

    # Passenger and luggage information
    num_adults = Column(Integer, nullable=False, default=1)
    num_children = Column(Integer, nullable=True, default=0)
    num_large_suitcases = Column(
        Integer, nullable=True, default=0
    )  # Trolley bags, large suitcases
    num_carryons = Column(Integer, nullable=True, default=0)
    num_backpacks = Column(Integer, nullable=True, default=0)
    num_other_bags = Column(
        Integer, nullable=True, default=0
    )  # Other bags, small items
    num_luggages = Column(Integer, nullable=True, default=0)  # Total luggage count
    num_passengers = Column(
        Integer, nullable=True, default=1) # Total passengers including adults and children
    # Passenger and luggage information - END

    # Car and fuel preferences
    preferred_car_type = Column(
        Enum(CarTypeEnum), nullable=True, default=CarTypeEnum.sedan
    )
    preferred_fuel_type = Column(
        Enum(FuelTypeEnum), nullable=True, default=FuelTypeEnum.diesel
    )
    in_car_amenities = Column(
        JSON, nullable=True
    )  # JSON/text list of in-car amenities (e.g., AC, music system, etc.)
    # Car and fuel preferences - END

  

    # Financial fields
    base_fare = Column(Float, nullable=True, default=0.0)  # Base fare for the trip
    driver_allowance = Column(
        Float, nullable=True, default=0.0
    )  # Daily driver allowance for outstation trips
    tolls_estimate = Column(
        Float, nullable=True, default=0.0
    )  # Estimated tolls for the trip
    parking_estimate = Column(
        Float, nullable=True, default=0.0
    )  # Estimated parking charges for the trip
    permit_fee = Column(
        Float, nullable=True, default=0.0
    )  # Interstate permit fee for outstation trips
    platform_fee = Column(
        Float, nullable=True, default=0.0
    )  # Platform fee charged by the system
    final_price = Column(Float, nullable=True, default=0.0)  # System-calculated
    final_display_price = Column(
        Float, nullable=True, default=0.0
    )  # Price shown to driver admin (final or quoted) w/o platform fee
    price_breakdown = Column(
        JSON, nullable=True 
    )  # JSON/text for detailed price breakdown (base fare, driver allowance, tolls, parking, etc.)
    overages = Column(
        JSON, nullable=True
    )  # JSON/text for overages (e.g., overage amount per km, overage estimate amount, etc.)

     
    # Inclusions and exclusions
    inclusions = Column(
        JSON, nullable=True
    )  # JSON/text list of inclusions (e.g., driver meals, tolls)
    exclusions = Column(
        JSON, nullable=True
    )  # JSON/text list of exclusions (e.g., fuel, parking, tolls
    # Inclusions and exclusions - END

    # Airport pickup/flight metadata
    flight_number = Column(String(32), nullable=True)
    terminal_number = Column(String(32), nullable=True)
    toll_road_preferred = Column(
        Boolean, default=False, nullable=False
    )  # Customer opted for toll road usage for faster trip. This is applicable only for airport trips.
    placard_required = Column(Boolean, nullable=True, default=False)
    placard_name = Column(String(128), nullable=True)
    # Airport pickup/flight metadata - END

    # Trip metadata
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
    # Trip metadata - END

    # Additional metadata
    estimated_km = Column(
        Float, nullable=True, default=0.0)  # Estimated distance for the trip
    indicative_overage_warning = Column(
        Boolean, default=False, nullable=False
    )  # does not apply to all hourly local trips
    alternate_customer_phone = Column(String(32), nullable=True)
    # Passenger info (nullable, for 'book for someone else' feature)
    passenger_id = Column(
        MySQL_CHAR(36),
        nullable=True,
    )
    hash= Column(
        String(255), nullable=True, unique=True
    )  # Hash for trip details to prevent duplicate bookings initiated by same user
    # Additional metadata - END
 
 
