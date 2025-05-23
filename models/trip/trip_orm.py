from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import Column, Integer, String, Enum, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from db.database import Base
import enum


class CreatorTypeEnum(str, enum.Enum):
    customer = "customer"
    driver = "driver"
    system = "system"


class Trip(Base):
    __tablename__ = "trips"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    creator_id = Column(Integer, nullable=False, index=True)
    creator_type = Column(
        Enum(CreatorTypeEnum),
        default=CreatorTypeEnum.customer,
        nullable=False,
    )
    trip_type = Column(Enum(TripTypeEnum), nullable=False)
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
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    num_passengers = Column(Integer, nullable=False)
    luggage_info = Column(String(255), nullable=True)
    preferred_car_type = Column(String(32), nullable=True)
    status = Column(
        Enum(TripStatusEnum), default=TripStatusEnum.created, nullable=False
    )
    base_fare = Column(Float, nullable=True)
    driver_allowance = Column(Float, nullable=True)
    tolls_estimate = Column(Float, nullable=True)
    parking_estimate = Column(Float, nullable=True)
    platform_fee = Column(Float, nullable=True)
    quoted_price = Column(Float, nullable=True)  # Customer's counter-quote
    final_price = Column(Float, nullable=True)  # System-calculated
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    status_audits = relationship("TripStatusAudit", back_populates="trip")


class TripStatusAudit(Base):
    __tablename__ = "trip_status_audits"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(MySQL_CHAR(36), ForeignKey("trips.id"), nullable=False)
    status = Column(Enum(TripStatusEnum), nullable=False)
    changed_by = Column(
        String(64), nullable=False
    )  # Could be 'customer', 'admin', etc.
    timestamp = Column(DateTime, server_default=func.now(), nullable=False)

    trip = relationship("Trip", back_populates="status_audits")
