from sqlalchemy.dialects.mysql import JSON  # or PostgreSQL JSONB
from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Index,
    String,
    DateTime,
    Integer,
    UniqueConstraint,
)
from db.database import Base
from sqlalchemy.dialects.mysql import CHAR
import uuid
from core.config import settings
from datetime import datetime, timezone
from sqlalchemy.orm import relationship

from datetime import datetime



class CustomerRecentLocation(Base):
    __tablename__ = "customer_recent_locations"

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

    place_id = Column(String(255), nullable=False, index=True, unique=False)
    provider = Column(String(50), default=settings.LOCATION_SERVICE_PROVIDER, nullable=False)

    location = Column(JSON, nullable=False, comment="Full location details as returned by the geocoding API, stored as JSON for flexibility")

    usage_count = Column(Integer, default=1)
    last_used_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at = Column(DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,)

    customer=relationship(
        "Customer",
        back_populates="recent_locations",
    )



    __table_args__ = (
        UniqueConstraint("customer_id", "place_id", name="unique_user_place"),
        Index("idx_user_recent", "customer_id", "last_used_at"),
    )