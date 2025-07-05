from sqlalchemy import (
    Column,
    ForeignKey,
    String,
    DateTime,
    func,
    Enum as SAEnum,
    JSON,
)
from core.security import RoleEnum
from db.database import Base
import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR


class ServiceableGeographyOrm(Base):
    """
    Serviceable Geography ORM model for managing service areas and boundaries per trip type.
    """

    __tablename__ = "serviceable_geographies"

    id = Column(
        String(36),  # Use String for UUID in MySQL
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )

    trip_type_id = Column(
        MySQL_CHAR(36), ForeignKey("trip_types_master.id"), nullable=False, index=True
    )  # Foreign key to trip type master
    
    # JSON field to store city names, airport place_ids, or state codes as per trip type
    service_area_cities = Column(JSON, nullable=True)  # For local trips
    airport_place_ids = Column(JSON, nullable=True)  # For airport trips
    service_area_state_codes = Column(JSON, nullable=True)  # For outstation trips
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


