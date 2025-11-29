from sqlalchemy import Boolean, Column, String, DateTime, func, Enum as SAEnum
from core.security import RoleEnum
from db.database import Base
import uuid
from sqlalchemy.orm import relationship

 
class CountryModel(Base):
    __tablename__ = "countries_master"
    id = Column(
        String(36),  # Use String for UUID in MySQL
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    country_name = Column(String(64), unique=True, nullable=False) # e.g. India
    country_code = Column(String(8), unique=True, nullable=False)  # e.g. IN
    phone_code = Column(String(8), unique=True, nullable=False)  # e.g. +91
    phone_number_regex = Column(String(255), nullable=False)  # e.g. ^[6-9]\d{9}$
    currency = Column(String(8), nullable=False, unique=True)  # e.g. INR
    currency_symbol = Column(String(8), nullable=False, unique=True)  # e.g. ₹
    distance_unit = Column(String(8), default="km", nullable=True, unique=True)  # e.g. km
    flag = Column(String(8), nullable=False, unique=True)  # e.g. 🇮🇳
    time_zone = Column(String(64), nullable=False, unique=True)  # e.g. Asia/Kolkata
    locale = Column(String(16), nullable=False, unique=True)  # e.g. en_IN
    
    # one-to-many relationship: a country has many states
    states = relationship("StateModel", back_populates="country", lazy="selectin", cascade="all, delete-orphan")

    # one-to-many relationship: a country has many regions
    regions = relationship(
        "RegionModel",
        back_populates="country",
        lazy="joined",
        cascade="all, delete-orphan",
    )
    is_serviceable = Column(Boolean, nullable=False, default=True)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_modified = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )