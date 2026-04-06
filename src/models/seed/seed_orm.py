import uuid
from sqlalchemy import Column
from sqlalchemy import Column, String, DateTime, func, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from datetime import datetime, timezone
from db.database import Base
from sqlalchemy import Enum as SAEnum

from models.seed.seed_enum import SeedKeyEnum


class SeedMetaData(Base):
    __tablename__ = "seed_metadata"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    key = Column(
        SAEnum(SeedKeyEnum, name="seed_key_enum"),
        nullable=False,
        unique=True,
        index=True,
    )
    value = Column(String(255), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("key", name="uq_seed_metadata_key"),)
