#ORM for admin user management
from sqlalchemy import (
    Column,
    DateTime,
    String,
    Boolean,
    Text,
    func,
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


class User(Base):
    __tablename__ = "users"
    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )
    name= Column(String(255), nullable=True)  # User's name
    username = Column(String(50), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=True, default=settings.CABBO_USER_DEFAULT_PASSWORD)  # Hashed password
    is_active = Column(Boolean, default=True, nullable=False)  # Active status
    role = Column(
        SqlEnum(RoleEnum, name="user_role_enum"),
        default=RoleEnum.super_admin,
        nullable=False,
    )  # User role (admin/user) System or super admin by default.

    #Secondaery data
    gender = Column(SqlEnum(GenderEnum, name="gender_enum"), nullable=True)
    dob = Column(DateTime, nullable=True)
    emergency_contact_name = Column(String(255), nullable=True)
    emergency_contact_number = Column(String(20), nullable=True)
    bearer_token = Column(Text, nullable=True) # Bearer token for authentication
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    
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