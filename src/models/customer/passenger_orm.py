from sqlalchemy import (
    Column,
    String,
    DateTime,
    Boolean,
    ForeignKey,
    Enum as SAEnum,
)
from sqlalchemy.dialects.mysql import CHAR
from core.security import RoleEnum
from db.database import Base
from sqlalchemy.sql import func
import uuid
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR




class Passenger(Base):
    __tablename__ = "passengers"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )
    customer_id = Column(
        MySQL_CHAR(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(DateTime, server_default=func.utc_timestamp(), nullable=False)
    last_modified = Column(
        DateTime,
        server_default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
        nullable=False,
    )
        # Relationship to Trip
    trips = relationship("Trip", back_populates="passenger")

    # Optionally, add more fields (e.g., email, relationship, etc.) as needed
