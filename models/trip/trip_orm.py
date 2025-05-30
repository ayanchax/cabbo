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
    creator_id = Column(Integer, nullable=False, index=True)
    creator_type = Column(
        Enum(RoleEnum),  # Assuming RoleEnum includes customer, driver, admin
        default=RoleEnum.customer,
        nullable=False,
    )
    # Trip details
    trip_type = Column(Enum(TripTypeEnum), nullable=False)
    # Location information
    origin_display_name = Column(String(255), nullable=False)
    origin_lat = Column(Float, nullable=False)
    origin_lng = Column(Float, nullable=False)
    origin_place_id = Column(String(128), nullable=True)
    origin_address = Column(String(255), nullable=True)
    destination_display_name = Column(String(255), nullable=False)
    destination_lat = Column(Float, nullable=False)
    destination_lng = Column(Float, nullable=False)
    destination_place_id = Column(String(128), nullable=True)
    destination_address = Column(String(255), nullable=True)
    hops = Column(Text, nullable=True)  # JSON/text list of hops for outstation
    is_interstate = Column(Boolean, default=False, nullable=False)
    is_round_trip = Column(Boolean, default=True, nullable=False)
    # Date and time information
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    # Passenger and luggage information
    num_adults = Column(Integer, nullable=False)
    num_children = Column(Integer, nullable=False)
    num_large_suitcases = Column(Integer, nullable=True)
    num_carryons = Column(Integer, nullable=True)
    num_backpacks = Column(Integer, nullable=True)
    num_other_bags = Column(Integer, nullable=True)
    num_luggages = Column(Integer, nullable=True)

    # Car and fuel preferences
    preferred_car_type = Column(Enum(CarTypeEnum), nullable=True)
    preferred_fuel_type = Column(Enum(FuelTypeEnum), nullable=True)

    # Driver assignment fields
    driver_name = Column(String(255), nullable=True)
    driver_phone = Column(String(32), nullable=True)
    car_model = Column(String(64), nullable=True)
    car_registration_number = Column(String(32), nullable=True)
    payment_mode = Column(String(32), nullable=True)  # gpay, phonepe, paytm
    payment_number = Column(String(32), nullable=True)  # UPI phone number

    status = Column(
        Enum(TripStatusEnum), default=TripStatusEnum.created, nullable=False
    )

    # Financial fields
    base_fare = Column(Float, nullable=True)
    driver_allowance = Column(Float, nullable=True)
    tolls_estimate = Column(Float, nullable=True)
    parking_estimate = Column(Float, nullable=True)
    permit_fee = Column(Float, nullable=True)
    platform_fee = Column(Float, nullable=True)
    quoted_price = Column(Float, nullable=True)  # Customer's counter-quote
    final_price = Column(Float, nullable=True)  # System-calculated
    final_display_price = Column(
        Float, nullable=True
    )  # Price shown to driver admin (final or quoted) w/o platform fee

    # Airport pickup/flight metadata
    flight_number = Column(String(32), nullable=True)
    terminal_number = Column(String(32), nullable=True)
    toll_road_preferred = Column(
        Boolean, default=False, nullable=False
    )  # Customer opted for toll road usage for faster trip. This is applicable only for airport trips.
    placard_required = Column(Boolean, nullable=True, default=False)
    placard_name = Column(String(128), nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    indicative_overage_warning = Column(
        Boolean, default=False, nullable=False
    )  # does not apply to all hourly local trips
    status_audits = relationship("TripStatusAudit", back_populates="trip")

    alternate_customer_phone = Column(String(32), nullable=True)

    # Passenger info (nullable, for 'book for someone else' feature)
    passenger_id = Column(
        MySQL_CHAR(36),
        ForeignKey("passengers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="FK to passengers table; null if trip is for self",
    )


class TripStatusAudit(Base):
    __tablename__ = "trip_status_audits"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(MySQL_CHAR(36), ForeignKey("trips.id"), nullable=False)
    status = Column(Enum(TripStatusEnum), nullable=False)
    changed_by = Column(
        String(64), nullable=False
    )  # Could be 'customer', 'admin', etc.
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
