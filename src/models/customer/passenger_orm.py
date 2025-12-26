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


class Passenger(Base):
    __tablename__ = "passengers"

    id = Column(
        CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
    )
    customer_id = Column(
        CHAR(36),
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    phone_number = Column(String(20), unique=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)
    created_at = Column(DateTime, server_default=func.utc_timestamp(), nullable=False)
    last_modified = Column(
        DateTime,
        server_default=func.utc_timestamp(),
        onupdate=func.utc_timestamp(),
        nullable=False,
    )

    # Optionally, add more fields (e.g., email, relationship, etc.) as needed
