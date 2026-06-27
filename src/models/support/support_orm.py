from datetime import datetime, timezone
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy.orm import relationship

from core.security import RoleEnum
from db.database import Base
from models.support.support_enum import SupportScopeEnum, SupportTypeEnum


class SupportContact(Base):
    __tablename__ = "support_contacts"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    display_name = Column(String(128), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    phone_number = Column(String(20), nullable=False, index=True)
    whatsapp_number = Column(String(20), nullable=True)
    support_type = Column(
        SAEnum(SupportTypeEnum, name="customer_support_type_enum"),
        nullable=False,
        default=SupportTypeEnum.customer,
        index=True,
    )
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
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
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    routing_rules = relationship(
        "SupportRoutingRule",
        back_populates="support_contact",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class SupportRoutingRule(Base):
    __tablename__ = "support_routing_rules"

    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        index=True,
    )
    support_contact_id = Column(
        MySQL_CHAR(36),
        ForeignKey("support_contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scope_type = Column(
        SAEnum(SupportScopeEnum, name="support_scope_enum"),
        nullable=False,
        index=True,
    )
    scope_id = Column(
        MySQL_CHAR(36),
        nullable=False,
        index=True,
        comment="ID of the country, state, or region selected by scope_type.",
    )
    country_id = Column(
        MySQL_CHAR(36),
        ForeignKey("countries_master.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    state_id = Column(
        MySQL_CHAR(36),
        ForeignKey("states_master.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    region_id = Column(
        MySQL_CHAR(36),
        ForeignKey("regions_master.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    trip_type_scope = Column(
        MySQL_CHAR(36),
        nullable=False,
        default="all",
        index=True,
        comment="Use 'all' or a TripTypeEnum value such as local/outstation.",
    )
    priority = Column(
        Integer,
        nullable=False,
        default=100,
        comment="Lower values win when multiple active support rules match.",
    )
    created_by = Column(MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value)
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
    is_active = Column(Boolean, nullable=False, default=True, index=True)

    support_contact = relationship(
        "SupportContact",
        back_populates="routing_rules",
    )
    country = relationship("CountryModel", lazy="joined")
    state = relationship("StateModel", lazy="joined")
    region = relationship("RegionModel", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "("
            "(scope_type = 'country' AND country_id = scope_id "
            "AND state_id IS NULL AND region_id IS NULL) OR "
            "(scope_type = 'state' AND state_id = scope_id "
            "AND country_id IS NULL AND region_id IS NULL) OR "
            "(scope_type = 'region' AND region_id = scope_id "
            "AND country_id IS NULL AND state_id IS NULL)"
            ")",
            name="ck_support_rule_scope_matches_geography",
        ),
        UniqueConstraint(
            "support_contact_id",
            "scope_type",
            "scope_id",
            "trip_type_scope",
            name="uq_support_contact_scope_trip_type",
        ),
    )
