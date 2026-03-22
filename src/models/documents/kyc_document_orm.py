import uuid
from sqlalchemy.dialects.mysql import CHAR as MySQL_CHAR
from sqlalchemy import Boolean, Column, DateTime, Enum, String
from sqlalchemy.sql import func
from db.database import Base
from core.security import RoleEnum
from models.documents.kyc_document_enum import KYCDocumentTypeEnum


class KYCDocumentTypes(Base):
    __tablename__ = "kyc_document_types"
    id = Column(
        MySQL_CHAR(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )

    document_type = Column(
        Enum(KYCDocumentTypeEnum), nullable=False
    )  # e.g., driver_license, aadhar_card
    document_alias = Column(
        String(255), nullable=True
    )  # e.g., Driver License, Aadhar Card
    document_description = Column(
        String(255), nullable=True
    )  # Option Description of the document type
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    created_by = Column(
        MySQL_CHAR(36), nullable=False, default=RoleEnum.system.value
    )  # Created by system, admin, or user
    last_modified = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
        comment="Indicates if the document type is active and can be used for KYC verification. Inactive types are not available for new document submissions but existing documents of that type remain unaffected.",
    )
