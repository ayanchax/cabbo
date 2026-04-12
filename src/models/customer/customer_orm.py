from sqlalchemy import (
    JSON,
    Column,
    String,
    DateTime,
    Integer,
    Boolean,
    Text,
    ForeignKey,
)
from sqlalchemy.dialects.mysql import CHAR
from db.database import Base
import uuid
from sqlalchemy.types import Enum as SqlEnum
from sqlalchemy.orm import relationship

from models.user.user_enum import GenderEnum
from datetime import datetime, timezone


class Customer(Base):
    __tablename__ = "customers"

    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    # Secondary data
    dob = Column(DateTime, nullable=True)
    gender = Column(SqlEnum(GenderEnum, name="gender_enum"), nullable=True)
    # Optional emergency contact for reaching someone on behalf of the customer
    # when neither their primary nor alternate phone number(provided in trip) is reachable.
    # Unlike the alternate_customer_phone in trip_orm.py (which is trip-specific),
    # this contact is platform-wide — used by support agents for account issues,
    # safety concerns, or critical trip emergencies.
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_number = Column(String(20), nullable=True)
    opt_in_updates = Column(
        Boolean, default=False, nullable=False
    )  # consent for offers/updates
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    is_phone_verified = Column(Boolean, default=False, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    last_modified = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    bearer_token = Column(Text, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    is_suspended = Column(
        Boolean,
        default=False,
        nullable=False,
        comment="Indicates if the customer is suspended from using the service due to policy violations or other disputes and issues.",
    )
    suspension_reason = Column(
        Text,
        nullable=True,
        comment="If the customer is suspended, this field can store the reason for suspension.",
    )
    s3_image_info = Column(
        JSON,
        nullable=True,
        comment="Stores S3 key and URL for the customer's profile picture if using S3 for storage.",
    )
    trip_ratings = relationship(
        "TripRating",
        back_populates="customer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )  # Ratings given by customer to one or more trips
    trips = relationship(
        "Trip",
        back_populates="customer",
        primaryjoin="and_(Customer.id == Trip.creator_id, Trip.creator_type == 'customer')",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PreOnboardingCustomer(Base):
    __tablename__ = "pre_onboarding_customers"

    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    otp_hash = Column(String(128), nullable=False)
    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_sent_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class CustomerEmailVerification(Base):
    __tablename__ = "customer_email_verification"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(
        CHAR(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    verification_url = Column(String(512), nullable=False, unique=True)
    expiry = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
