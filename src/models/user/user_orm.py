# ORM for admin user management
from sqlalchemy import (
    JSON,
    Column,
    String,
    DateTime,
    Boolean,
    Text,
    ForeignKey,
    Index,
)
from sqlalchemy.dialects.mysql import CHAR
from core.security import RoleEnum
from db.database import Base
import uuid
from sqlalchemy.types import Enum as SqlEnum
from core.config import settings

from models.user.user_enum import GenderEnum
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from datetime import datetime, timezone

from typing import Union


from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"
    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )
    name = Column(String(255), nullable=True)  # User's name
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    password_hash = Column(
        String(255), nullable=True, default=settings.CABBO_USER_DEFAULT_PASSWORD
    )  # Hashed password
    is_active = Column(Boolean, default=True, nullable=False)  # Active status
    role = Column(
        SqlEnum(RoleEnum, name="user_role_enum"),
        default=RoleEnum.super_admin,
        nullable=False,
    )  # User role (admin/user) System or super admin by default.

    # Secondaery data
    gender = Column(SqlEnum(GenderEnum, name="gender_enum"), nullable=True)
    dob = Column(DateTime, nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_number = Column(String(20), nullable=True)
    bearer_token = Column(Text, nullable=True)  # Bearer token for authentication
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # Intentionally we are not having image field for system users, as we
    # we do not want to store images for system users, and it is not a critical information for them.
    last_modified = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_by = Column(
        MySQL_CHAR(36),
        nullable=False,
        default=RoleEnum.system.value,
    )  # Role of the user who created this record


class SystemUserSession(Base):
    __tablename__ = "system_user_sessions"

    # Primary key
    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )

    # Associated user_id with the session
    user_id: str = Column(
        CHAR(36),
        ForeignKey("users.id", ondelete="CASCADE"),
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

    # When was the session created, defaults to current date time, trivially.
    created_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # When the user was last seen requesting user facing protected resource from an active or inactive session.
    last_seen_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,  # Update this every n minutes from current value of last_seen_id, this is essentially for monitoring activity of user recently in system.
    )

    # When the hashed token is set to expire
    expires_at: datetime = Column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )

    # When was the hashed token revoked
    revoked_at: Union[datetime, None] = Column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Useful for showing active sessions across devices and browsers and to detect suspicious login etc.
    # However, we will never treat these as
    # strong identity/device-binding signals.
    user_agent: Union[str, None] = Column(
        String(512),
        nullable=True,
    )

    # Track ip address from request
    ip_address: Union[str, None] = Column(
        String(45),
        nullable=True,
    )

    location: Union[str, None] = Column(
        String(120),
        nullable=True,  # City/region from login was detected.
    )

    is_active: bool = Column(
        Boolean,
        nullable=False,
        default=True,  # Whether session is active, this does the same thing as revoked_at does by not being present at all. This is just a quick bool check instead of doing revoked_at is None to check if session is active, both columns are complementary to each other. revoked_at is especially used for auditability.
    )

    # Any additional metadata we want to store while registering a user session.
    session_metadata: dict = Column(JSON, nullable=True, default=None)

    # Every session must have one admin user associated with it.
    user = relationship("User")

    __table_args__ = (
        Index(
            "ix_sys_user_sessions_user_id_is_active",
            "user_id",
            "is_active",
        ),
    )
