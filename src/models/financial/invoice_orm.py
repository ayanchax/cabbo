"""Invoice identity and storage metadata; generation and delivery come later."""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Column, Date, DateTime, ForeignKey, String
from sqlalchemy.dialects.mysql import CHAR

from db.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment="Stable internal invoice identifier.")
    entity_id = Column(CHAR(36), ForeignKey("trips.id"), nullable=False, comment="Trip for which this invoice was issued.")
    invoice_number = Column(String(64), nullable=False, unique=True, comment="Unique customer-facing invoice number.")
    invoice_date = Column(Date, nullable=False, comment="Legal issue date of the invoice.")
    s3_object_key = Column(String(1024), nullable=True, comment="Persistent private PDF object key; never an expiring presigned URL.")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), comment="UTC timestamp when this invoice record was created.")
