from core.security import RoleEnum
from models.trip.trip_enums import (
    TripStatusEnum,
    TripTypeEnum,
    FuelTypeEnum,
    CarTypeEnum,
)
import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import (
    JSON,
    Column,
    Index,
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
from db.database import Base
from datetime import datetime, timezone

class Trip(Base):
    __tablename__ = "trips"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    booking_id = Column(
        String(64), nullable=False, unique=True, index=True
    )  # Unique booking reference ID which is shown to customer and driver
    #  Creator information
    creator_id = Column(
        MySQL_CHAR(36),
        ForeignKey("customers.id"),  # Explicitly define the foreign key
        nullable=False,
        index=True,
    )
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
    origin = Column(JSON, nullable=False)  # Origin city name
    destination = Column(JSON, nullable=False)  # Destination city name
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
    start_datetime = Column(DateTime, nullable=False) #This field is always converted to UTC, refer validate_date_time() method in utility.py for details
    expected_end_datetime = Column(
        DateTime, nullable=True
    )  # Nullable | for local trips, we set it by package chosen
    end_datetime = Column(DateTime, nullable=True) #This field is always converted to UTC, refer validate_date_time() method in utility.py for details
    total_days = Column(
        Integer, nullable=False, default=1
    )  # Total days for outstation trips
    included_kms = Column(
        Float, nullable=True, default=0.0
    )  # Included km for hourly rental trips and outstation trips
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
        Integer, nullable=True, default=1
    )  # Total passengers including adults and children

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
        MySQL_CHAR(36),
        ForeignKey("drivers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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
    tolls = Column(Float, nullable=True, default=0.0)  #  tolls for the trip
    parking = Column(Float, nullable=True, default=0.0)  #  parking charges for the trip
    permit_fee = Column(
        Float, nullable=True, default=0.0
    )  # Interstate permit fee for outstation trips
    platform_fee = Column(
        Float, nullable=True, default=0.0
    )  # Platform fee charged by the system is the fixed plus dynamic convenience fee
    final_price = Column(Float, nullable=True, default=0.0)  # System-calculated
    final_display_price = Column(
        Float, nullable=True, default=0.0
    )  # Price shown to driver admin (final) w/o platform fee/convenience fee
    advance_payment = Column(
        Float, nullable=True, default=0.0
    )  # Advance payment made by customer(generally the platform fee/convenience fee), if any
    balance_payment = Column(
        Float, nullable=True, default=0.0
    )  # Balance payment to be made by customer after trip completion

    
    payment_provider_metadata = Column(
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
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    # Trip metadata - END

    # Additional metadata
    special_needs_requests = Column(
        Text, nullable=True
    )  # Special needs or requests from customer, essentially customer notes that customer can update before trip starts[created, confirmed]

    estimated_km = Column(
        Float, nullable=True, default=0.0
    )  # Estimated distance for the trip
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

    is_active = Column(
        Boolean, nullable=False, default=True
    )  # Soft delete flag for trip record, which only super admins can toggle to false in case of any fraudulent or test trips that need to be deactivated, but we don't want to delete the record from the database for data integrity and audit purposes. When a trip is marked as inactive, it will be excluded from all active trip listings and queries in the system, but the record will still exist in the database with is_active set to false.
    # Additional metadata - END

    # Audit fields
    status_audits = relationship("TripStatusAudit", back_populates="trip")
    driver = relationship("Driver", back_populates="trips")
    package = relationship("TripPackageConfig", back_populates="trips")
    trip_type_master = relationship("TripTypeMaster", back_populates="trips")
    passenger = relationship("Passenger", back_populates="trips")
    customer = relationship(
        "Customer",
        back_populates="trips",
        primaryjoin="and_(Trip.creator_id == Customer.id, Trip.creator_type == 'customer')",
    )
    # A trip can have one driver earning record associated with it, which is populated when the trip is completed and the driver payment is settled from Cabbo's end, so the relationship is one-to-one from Trip to DriverEarning and many-to-one from DriverEarning to Trip.
    driver_earning = relationship(
        "DriverEarning",
        back_populates="trip",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    trip_rating = relationship(
        "TripRating",
        back_populates="trip",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )  # A trip can have only one rating given by the customer but a driver can have multiple ratings from different customers for different trips, so the relationship is one-to-one from Trip to TripRating and one-to-many from Driver to TripRating.

    refund = relationship(
        "Refund",
        primaryjoin="Refund.entity_id==Trip.id",
        foreign_keys="[Refund.entity_id]",
        uselist=False,
        back_populates="trip",
        passive_deletes=True,
    )  # One-to-one relationship to Refund table based on entity_id, which is populated when a refund is initiated for the trip and the refund record is created in the refunds table.

    #A trip can have one dispute associated with it, which is populated when a dispute is raised for the trip, so the relationship is one-to-one from Trip to Dispute and many-to-one from Dispute to Trip.
    dispute = relationship(
        "Dispute",
        primaryjoin="Dispute.entity_id==Trip.id",
        foreign_keys="[Dispute.entity_id]",
        uselist=False,
        back_populates="trip",
        passive_deletes=True,
    )
    #A trip can have one cancellation record associated with it, which is populated when a trip is cancelled and the cancellation record is created in the cancellations table, so the relationship is one-to-one from Trip to Cancellation and many-to-one from Cancellation to Trip.
    cancellation = relationship(
        "Cancellation",
        primaryjoin="Cancellation.entity_id==Trip.id",
        foreign_keys="[Cancellation.entity_id]",
        uselist=False,
        back_populates="trip",
        passive_deletes=True,
    )
    
    # Audit fields - END


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
    committer_id = Column(
        MySQL_CHAR(36), nullable=False, index=True
    )  # ID of the user who changed the status
    reason = Column(String(255), nullable=True)  # New: reason/message for audit
    timestamp =  Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)



    trip = relationship("Trip", back_populates="status_audits")


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
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_modified = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, nullable=False, default=True)
    trips = relationship("Trip", back_populates="trip_type_master")


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
    # Since Trip Package applies to local/hourly rental trips, so region_id is set to configure region-specific packages
    region_id = Column(
        MySQL_CHAR(36),
        ForeignKey("regions_master.id"),
        nullable=True,  # Nullable for backward compatibility or "default" packages
        index=True,
        comment="FK to regions_master; null means applies to all regions",
    )
    included_hours = Column(Integer, nullable=False)  # e.g., 4, 6, 8, 10, 12
    included_km = Column(Integer, nullable=False)  # e.g., 40, 60, 80, 100, 120
    driver_allowance = Column(
        Float, nullable=True, default=0.0
    )  # Daily driver allowance for outstation/local trips
    package_label = Column(String(64), nullable=False)
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_modified = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    is_active = Column(Boolean, nullable=False, default=True)
    # Relationship to Trip
    trips = relationship("Trip", back_populates="package")

    # Add composite unique constraint: (trip_type_id, region_id, package_label)
    __table_args__ = (
        Index(
            "ix_trip_package_region",
            "trip_type_id",
            "region_id",
            "package_label",
            unique=True,
        ),
    )
