from core.security import RoleEnum
from models.trip.trip_enums import (
    TripStatusEnum,
    TripTypeEnum,
    FuelTypeEnum,
    CarTypeEnum,
    CancellationSubStatusEnum,
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
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base


class Trip(Base):
    __tablename__ = "trips"

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
        MySQL_CHAR(36), ForeignKey("trip_types_master.id"), nullable=False, index=True
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
    is_round_trip = Column(Boolean, default=False, nullable=False)
    # Location information - END

    # Package information selected by customer
    # This is applicable only for hourly rental trips
    package_id = Column(
        MySQL_CHAR(36), ForeignKey("trip_package_config.id"), nullable=True, index=True
    )
    package_label = Column(
        String(255), nullable=True, default=None
    )  # Label for the package, e.g., "4 Hours / 40 KM" 
    package_label_short = Column(
        String(100), nullable=True, default=None
    )  # Short label for the package, e.g., "4H/40KM" 
    # FK to trip package config table for hourly rental trips
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

    # Driver assignment fields
    driver_id = Column(
        MySQL_CHAR(36), ForeignKey("drivers.id", ondelete="SET NULL"), nullable=True, index=True
    )  # Nullable: Driver assigned to the trip, if any
    # Driver assignment fields -END

    status = Column(
        Enum(TripStatusEnum), default=TripStatusEnum.created, nullable=False
    )

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
    quoted_price = Column(Float, nullable=True)  # Customer's counter-quote
    final_price = Column(Float, nullable=True, default=0.0)  # System-calculated
    final_display_price = Column(
        Float, nullable=True, default=0.0
    )  # Price shown to driver admin (final or quoted) w/o platform fee/convenience fee
    advance_payment = Column(
        Float, nullable=True, default=0.0
    )  # Advance payment made by customer(generally the platform fee/convenience fee), if any
    balance_payment = Column(
        Float, nullable=True, default=0.0
    )  # Balance payment to be made by customer after trip completion
    payment_provider_metadata= Column(
        JSON, nullable=True
    )  # JSON/text for payment details (e.g., payment mode, transaction ID, etc.)
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
        ForeignKey("passengers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK to passengers table; null if trip is for self",
    )
    # Additional metadata - END

    #Audit fields
    status_audits = relationship("TripStatusAudit", back_populates="trip")
    driver = relationship("Driver", back_populates="trips")
    driver_earnings = relationship(
        "DriverEarnings", back_populates="trip", cascade="all, delete-orphan", passive_deletes=True
    )
    driver_ratings = relationship(
        "DriverRating", back_populates="trip", cascade="all, delete-orphan", passive_deletes=True
    )

    #Audit fields - END



class TripStatusAudit(Base):
    __tablename__ = "trip_status_audits"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_id = Column(MySQL_CHAR(36), ForeignKey("trips.id"), nullable=False)
    status = Column(Enum(TripStatusEnum), nullable=False)
    changed_by = Column(
        Enum(RoleEnum),  # Assuming RoleEnum includes customer, driver, admin
        default=RoleEnum.customer,
        nullable=True,
    )
    committer_id = Column(
        MySQL_CHAR(36), nullable=False, index=True
    )  # ID of the user who changed the status
    reason = Column(String(255), nullable=True)  # New: reason/message for audit
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)

    # New: for analytics and auditability
    cancellation_sub_status = Column(
        Enum(CancellationSubStatusEnum),
        nullable=True,
        default=None,
        comment="Detailed cancellation reason for analytics (nullable, only for cancelled trips)",
    )
    # Nullable: Only populated when cancellation_sub_status == CancellationSubStatusEnum.customer_preferences_not_met
    responsible_preference_keys_for_cancelation = Column(
        Text,  # Use Text for flexibility; can store comma-separated or JSON string
        nullable=True,
        comment="Snapshot of preference keys/flags at status change (nullable)",
    )

    trip = relationship("Trip", back_populates="status_audits")


class OutstandingDue(Base):
    __tablename__ = "outstanding_dues"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(MySQL_CHAR(36), ForeignKey("trips.id"), nullable=False)
    customer_id = Column(MySQL_CHAR(36), ForeignKey("customers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    reason = Column(String(255), nullable=False)
    created_by = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.system)
    # Nullable: Only populated when
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class TripTypeMaster(Base):
    __tablename__ = "trip_types_master"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type = Column(Enum(TripTypeEnum), nullable=False, unique=True)
    display_name = Column(String(64), nullable=False)
    description = Column(String(255), nullable=True)
    created_by = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )


class TripPackageConfig(Base):
    __tablename__ = "trip_package_config"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    trip_type_id = Column(
        MySQL_CHAR(36), ForeignKey("trip_types_master.id"), nullable=False, index=True
    )
    included_hours = Column(Integer, nullable=False)  # e.g., 4, 6, 8, 10, 12
    included_km = Column(Integer, nullable=False)  # e.g., 40, 60, 80, 100, 120
    driver_allowance = Column(
        Float, nullable=True, default=0.0
    )  # Daily driver allowance for outstation/local trips
    package_label = Column(String(64), nullable=False, unique=True)
    created_by = Column(Enum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, nullable=False, default=func.utc_timestamp())
    last_modified = Column(
        DateTime,
        nullable=False,
        default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
    )
