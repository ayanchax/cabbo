from sqlalchemy import Boolean, Column, Integer, String, DateTime, func, Enum as SAEnum
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
    phone_min_length = Column(Integer, default=10, nullable=False)  # e.g. 10
    phone_max_length = Column(Integer, default=10, nullable=False)  # e.g. 10
    phone_example = Column(String(32), nullable=True)  # e.g. +919876543210
    postal_code_regex = Column(String(255), nullable=False)  # e.g. ^\d{6}$
    postal_code_example = Column(String(32), nullable=True)  # e.g. 560001
    postal_code_min_length = Column(Integer, default=6, nullable=False)  # e.g. 6
    postal_code_max_length = Column(Integer, default=6, nullable=False)  # e.g. 6
    currency = Column(String(8), nullable=False, unique=True)  # e.g. INR
    currency_symbol = Column(String(8), nullable=False, unique=True)  # e.g. ₹
    currency_decimal_places = Column(Integer, nullable=False, default=2)  # e.g. 2 for paise in INR
    currency_in_words = Column(String(32), nullable=False, unique=True, default="Rupees")  # e.g. Rupees
    currency_international_name = Column(String(32), nullable=False, unique=True, default="Indian Rupee")  # e.g. Indian Rupee
    currency_symbol_position = Column(String(8), nullable=False, default="before")  # whether currency symbol is placed before or after the amount, e.g. ₹100 or 100¥
    currency_code_position = Column(String(8), nullable=False, default="after")  # whether currency code is placed before or after the amount, e.g. 100 INR or USD 100
    currency_thousand_separator = Column(String(8), nullable=False, default=",")  # e.g. 1,00,000
    currency_decimal_separator = Column(String(8), nullable=False, default=".")  # e.g. 100.50
    currency_lowest_unit_name = Column(String(32), nullable=False, unique=True, default="Paise")  # e.g. Paise
    currency_lowest_unit_conversion_factor = Column(Integer, nullable=False, default=100)  # e.g. 100 (1 Rupee = 100 paise)
    distance_unit = Column(String(8), default="km", nullable=True, unique=True)  # e.g. km
    flag = Column(String(8), nullable=False, unique=True)  # e.g. 🇮🇳
    time_zone = Column(String(64), nullable=False, unique=True)  # e.g. Asia/Kolkata
    locale = Column(String(16), nullable=False, unique=True)  # e.g. en_IN
    is_default = Column(Boolean, nullable=False, default=False) # whether this is the default country in the system
    # If user's request fails to determine country, we will use this default country for applying country-specific rules such as phone validation, currency, etc.
    # one-to-many relationship: a country has many states
    states = relationship("StateModel", back_populates="country", lazy="selectin", cascade="all, delete-orphan")
    min_age_for_drivers = Column(Integer, nullable=False, default=18)  # Minimum age required to register as a driver in this country
    min_age_for_customers = Column(Integer, nullable=False, default=13)  # Minimum age required to register as a customer in this country
    max_age_for_drivers = Column(Integer, nullable=False, default=90)  # Maximum age limit to register as a driver in this country
    max_age_for_customers = Column(Integer, nullable=False, default=90)  # Maximum age limit to register as a customer in this country
    min_age_for_system_users = Column(Integer, nullable=False, default=18)  # Minimum age required to register as a system user in this country
    max_age_for_system_users = Column(Integer, nullable=False, default=90)  # Maximum age limit to register as a system user in this country
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