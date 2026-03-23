from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    ForeignKey,
    String,
    DateTime,
)
from core.security import RoleEnum
from db.database import Base
import uuid
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from datetime import datetime, timezone


# Region or Metro Area City ORM model
class RegionModel(Base):
    # Region is a city or metro area within a state or province within a country
    # Region is the smallest geography unit for trip operations, all other geographies (State, Country) are linked via foreign keys
    # Any kind of granular service area definition (trip wise service availability, 'trip-cab-fuel' wise pricing, airport boundaries, fuel type support, cab type availability etc.) are mapped at the lowest level i.e, regions

    __tablename__ = "regions_master"
    id = Column(
        String(36),  # Use String for UUID in MySQL
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    region_name = Column(
        String(64), unique=True, nullable=False
    )  # e.g. Bangalore, Chennai
    alt_region_names=Column(JSON, nullable=True)  # e.g. ["Bengaluru", "Bangalore City"]
    region_code = Column(String(8), unique=True, nullable=False)  # e.g. BLR
    alt_region_codes = Column(
        JSON, nullable=True 
    )  # e.g. ["BLR", "BNG", "BANG", "BENG", "BEN"] #This is added to support multiple region codes returned by different location service providers
    # new normalized relation to StateModel
    state_id = Column(
        String(36),
        ForeignKey("states_master.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # 1 Region has 1 State
    state = relationship("StateModel", back_populates="regions", lazy="joined")

    trip_types = Column(
        JSON, nullable=True
    )  # Comma-separated list of trip types IDs from trip_types_master
    fuel_types = Column(
        JSON, nullable=True
    )  # Comma-separated list of fuel type IDs from fuel_types_master
    car_types = Column(
        JSON, nullable=True
    )  # Comma-separated list of car type IDs from car_types_master
    airport_locations = Column(
        JSON, nullable=True
    )  # Comma separated list of airport location IDs from airports_master
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)

    # foreign key + relationship to CountryModel (one country per region)
    country_id = Column(
        String(36),
        ForeignKey("countries_master.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 1 Region has 1 Country
    country = relationship("CountryModel", back_populates="regions")

    is_serviceable = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_modified = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
     

