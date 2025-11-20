from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    String,
    DateTime,
    func,
    Enum as SAEnum,
)
from core.security import RoleEnum
from db.database import Base
import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR


class ServiceableAreaModel(Base):
    """
    Serviceable Geography ORM model for managing service areas and boundaries per trip type.
    """

    __tablename__ = "serviceable_areas"

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

    serviceable_areas = Column(
        JSON, nullable=True
    )  # List of region codes for the trip type validated by ServiceableAreaSchema
    # e.g [{
    #        "country_code": "IN",
    #        "state_code": "KA",
    #        "region_code": "BLR"}]
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
