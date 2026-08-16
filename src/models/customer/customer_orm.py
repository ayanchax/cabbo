from typing import Union

from sqlalchemy import (
    JSON,
    Column,
    String,
    DateTime,
    Integer,
    Boolean,
    Text,
    ForeignKey,
    Index,
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
    __table_args__ = (
        Index("ix_customers_active_created", "is_active", "created_at"),
        Index(
            "ix_customers_verification_flags",
            "is_active",
            "is_phone_verified",
            "is_email_verified",
        ),
    )

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

    recent_locations = relationship(
        "CustomerRecentLocation",
        back_populates="customer",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PreOnboardingCustomer(Base):
    # Table containing the volatile state of a customer while they login or register with Cabbo.
    __tablename__ = "pre_onboarding_customers"
    __table_args__ = (Index("ix_pre_onboarding_expires_at", "expires_at"),)

    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    otp_hash = Column(String(128), nullable=False, index=True)
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


class CustomerSession(Base):
    __tablename__ = "customer_sessions"

    #Primary key
    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )

    #Associated customer_id with the session
    customer_id: str = Column(
        CHAR(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # One way SHA-256 fingerprint/digest encoded as 64 hexadecimal characters. This is formed from a secured url safe token
    token_hash: str = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
    )

    #When was the session created, defaults to current date time, trivially.
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )

    #When the customer was last seen requesting customer facing protected resource from an active or inactive session.
    last_seen_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False, #Update this every n minutes from current value of last_seen_id, this is essentially for monitoring activity of user recently in system.
    )

    #When the hashed token is set to expire
    expires_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    #When was the hashed token revoked
    revoked_at: Union[datetime, None] = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Useful for showing active sessions across devices and browsers and to detect suspicious login etc. 
    # For example: If usual login from customer is from an IP location Mumbai, but suddenly we detect a login from
    # Delhi(very much possible - if user travels) - we will just send a suspicious activity email
    # to the customer registered email address to alert them and they can ignore if they did it otherwise they 
    # are advised to reach out to us to remove all active sessions as a security measure. This can be detected while 
    # the otp verify endpoint satisifies the otp equality and we are just about to 
    # rotate the hashed token, we can deterministically check all of these login activity and send alerts if needed.
    # We will do this post V1 - because in V1 - we are focussed on bagging more customers and not restrict or scare them to
    # use the application.
    # However, we will never treat these as
    # strong identity/device-binding signals.
    user_agent: Union[str, None] = Column(
        String(512),
        nullable=True,
    )

    #Track ip address from request
    ip_address: Union[str, None] = Column(
        String(45),
        nullable=True,
    )

    location:Union[str, None] = Column(
        String(120),
        nullable=True, #City/region from login was detected.
    )

    is_active: bool = Column(
        Boolean,
        nullable=False,
        default=True, #Whether session is active, this does the same thing as revoked_at does by not being present at all. This is just a quick bool check instead of doing revoked_at is None to check if session is active, both columns are complementary to each other. revoked_at is especially used for auditability.
    )

    #Any additional metadata we want to store while registering a customer session.
    session_metadata:dict=Column(JSON, nullable=True, default = None) 

    #Every session must have one customer associated with it.
    customer = relationship("Customer")

    __table_args__ = (
        Index(
            "ix_customer_sessions_customer_id_is_active",
            "customer_id",
            "is_active",
        ),
    )
