from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR

from core.security import RoleEnum
from db.database import Base


class TaxConfiguration(Base):
    __tablename__ = "tax_configurations"
    __table_args__ = (
        UniqueConstraint(
            "country_id",
            "tax_type",
            "tax_scope",
            "effective_from",
            name="uq_tax_country_type_scope_effective_from",
        ),
        Index("ix_tax_country_scope_active", "country_id", "tax_scope", "is_active"),
    )

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    country_id = Column(
        MySQL_CHAR(36),
        ForeignKey("countries_master.id"),
        nullable=False,
        index=True,
        comment="Country this tax configuration applies to.",
    )
    tax_type = Column(
        String(32),
        nullable=False,
        default="GST",
        comment="Tax family, e.g. GST.",
    )
    tax_scope = Column(
        String(64),
        nullable=False,
        comment="Taxable charge scope, e.g. platform_fee, ride_fee.",
    )
    rate_percent = Column(
        Float,
        nullable=False,
        comment="Tax rate percentage, e.g. 18.0 for 18% GST.",
    )
    effective_from = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    effective_to = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_modified = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
