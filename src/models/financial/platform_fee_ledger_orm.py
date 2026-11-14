"""Charge-time snapshots and separate refund adjustments; amounts are INR units.

Tax allocations and reporting dates remain unset until their treatment is known.
Financial history must not cascade-delete when an operational record is deleted.
"""
from datetime import datetime, timezone
import uuid

from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.mysql import CHAR

from db.database import Base


class PlatformFeeCollection(Base):
    __tablename__ = "platform_fee_collections"
    __table_args__ = (
        UniqueConstraint("provider", "payment_id", name="uq_platform_fee_collection_payment"),
        Index("ix_platform_fee_collection_captured", "captured_at"),
        Index("ix_platform_fee_collection_reporting", "reporting_date"),
        Index("ix_platform_fee_collection_entity", "entity_id"),
    )

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment='Stable internal ledger record identifier.')
    entity_id = Column(CHAR(36), ForeignKey("trips.id"), nullable=False, comment='Trip reference, matching the entity_id used by refunds.')
    provider = Column(String(32), nullable=False, comment='Payment provider identifier, for example razorpay.')
    payment_id = Column(String(64), nullable=False, comment='Captured provider payment identifier; unique together with provider.')
    order_id = Column(String(255), nullable=False, comment='Provider order associated with the captured payment.')
    payment_status = Column(String(32), nullable=False, comment='Verified provider payment status at collection capture.')
    currency = Column(String(3), nullable=False, comment='ISO 4217 currency code; monetary values use major currency units.')
    captured_amount = Column(Numeric(18, 2), nullable=False, comment='Total payment amount captured by the provider, before gateway deductions.')
    captured_at = Column(DateTime(timezone=True), nullable=True, comment='Provider capture timestamp when available; never substitute verification time.')
    base_fare = Column(Numeric(18, 2), nullable=True, comment='Historical trip base fare reference; not platform-fee revenue.')
    platform_fee_base = Column(Numeric(18, 2), nullable=True, comment='Taxable fee base excluding GST; null for unresolved historical breakdowns.')
    platform_fee_tax = Column(Numeric(18, 2), nullable=True, comment='Actual GST charged; null for unresolved historical breakdowns.')
    platform_fee_gross = Column(Numeric(18, 2), nullable=False, comment='Platform-fee base plus GST actually charged.')
    tax_configuration_id = Column(CHAR(36), ForeignKey("tax_configurations.id"), nullable=True, comment='Tax configuration applied at charge time; historical values remain snapshotted.')
    tax_type = Column(String(32), nullable=True, comment='Tax family applied at charge time, for example GST.')
    tax_rate_percent = Column(Numeric(7, 4), nullable=True, comment='Historical tax percentage applied to the fee base.')
    cgst_amount = Column(Numeric(18, 2), nullable=True, comment='Central GST amount; null when allocation is unresolved.')
    sgst_amount = Column(Numeric(18, 2), nullable=True, comment='State GST amount; null when allocation is unresolved.')
    igst_amount = Column(Numeric(18, 2), nullable=True, comment='Integrated GST amount; null when allocation is unresolved.')
    supplier_state_code = Column(String(2), nullable=True, comment='Two-digit GST state code of the supplier.')
    place_of_supply_state_code = Column(String(2), nullable=True, comment='Two-digit GST state code for the determined place of supply.')
    customer_id = Column(CHAR(36), ForeignKey("customers.id", ondelete="RESTRICT", name="fk_platform_fee_collection_customer"), nullable=True, comment='Customer reference; hard deletion is restricted while financial history references this customer.')
    customer_gstin = Column(String(15), nullable=True, comment='Customer GSTIN snapshot, when supplied.')
    customer_billing_state_code = Column(String(2), nullable=True, comment='Customer billing GST state code snapshot, when available.')
    reporting_date = Column(Date, nullable=True, comment='Applicable tax reporting date; independent of cash movement and nullable pending review.')
    review_required = Column(Boolean, nullable=False, default=True, server_default="1", comment='Whether unresolved data or tax treatment requires review before filing.')
    review_reason = Column(String(255), nullable=True, comment='Reason this record requires reporting review.')
    invoice_id = Column(CHAR(36), ForeignKey("invoices.id"), nullable=True, comment='Final invoice foreign key; null until an invoice is issued.')
    receipt_reference = Column(String(64), nullable=True, comment='Advance receipt document reference, where applicable.')
    refund_status = Column(String(32), nullable=False, default="unrefunded", server_default="unrefunded", comment='Derived collection summary: unrefunded, partially_refunded or fully_refunded.')
    refunded_base = Column(Numeric(18, 2), nullable=False, default=0, server_default="0", comment='Cumulative successfully refunded taxable fee base; adjustment rows store individual refunds.')
    refunded_tax = Column(Numeric(18, 2), nullable=False, default=0, server_default="0", comment='Cumulative successfully refunded GST; adjustment rows store individual refunds.')
    refunded_gross = Column(Numeric(18, 2), nullable=False, default=0, server_default="0", comment='Cumulative successfully refunded gross platform fee.')
    source = Column(String(32), nullable=False, comment='Record provenance, such as reconciliation or historical backfill.')
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), comment='UTC timestamp when the ledger record was created.')


class PlatformFeeRefundAdjustment(Base):
    __tablename__ = "platform_fee_refund_adjustments"
    __table_args__ = (
        UniqueConstraint("provider", "provider_refund_id", name="uq_platform_fee_adjustment_provider_refund"),
        UniqueConstraint("refund_id", name="uq_platform_fee_adjustment_refund"),
        Index("ix_platform_fee_adjustment_collection", "collection_id"),
        Index("ix_platform_fee_adjustment_processed", "processed_at"),
        Index("ix_platform_fee_adjustment_reporting", "reporting_date"),
    )

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()), comment='Stable internal ledger record identifier.')
    collection_id = Column(CHAR(36), ForeignKey("platform_fee_collections.id"), nullable=False, comment='Original captured collection being adjusted.')
    entity_id = Column(CHAR(36), ForeignKey("trips.id"), nullable=False, comment='Trip reference, matching the entity_id used by refunds.')
    refund_id = Column(CHAR(36), ForeignKey("refunds.id"), nullable=False, comment='Existing refunds table primary key for this successful adjustment.')
    provider = Column(String(32), nullable=False, comment='Payment provider identifier, for example razorpay.')
    provider_refund_id = Column(String(64), nullable=False, comment='Successful provider refund identifier; unique together with provider.')
    currency = Column(String(3), nullable=False, comment='ISO 4217 currency code; monetary values use major currency units.')
    # Missing historical allocations remain reviewable rather than guessed.
    refunded_base = Column(Numeric(18, 2), nullable=True, comment='Taxable fee base reversed by this refund; null when allocation is unresolved.')
    refunded_tax = Column(Numeric(18, 2), nullable=True, comment='GST reversed by this refund; null when allocation is unresolved.')
    refunded_gross = Column(Numeric(18, 2), nullable=False, comment='Gross platform-fee amount reversed by this successful refund.')
    cgst_amount = Column(Numeric(18, 2), nullable=True, comment='Central GST amount; null when allocation is unresolved.')
    sgst_amount = Column(Numeric(18, 2), nullable=True, comment='State GST amount; null when allocation is unresolved.')
    igst_amount = Column(Numeric(18, 2), nullable=True, comment='Integrated GST amount; null when allocation is unresolved.')
    processed_at = Column(DateTime(timezone=True), nullable=False, comment='UTC provider refund completion timestamp; does not determine GST reporting date.')
    reporting_date = Column(Date, nullable=True, comment='Applicable tax reporting date; independent of cash movement and nullable pending review.')
    document_type = Column(String(32), nullable=True, comment='Adjustment document kind, such as credit_note or refund_voucher.')
    document_number = Column(String(64), nullable=True, comment='Adjustment document number, when issued.')
    document_date = Column(Date, nullable=True, comment='Adjustment document issue date, independent of provider processing.')
    review_required = Column(Boolean, nullable=False, default=True, server_default="1", comment='Whether unresolved data or tax treatment requires review before filing.')
    review_reason = Column(String(255), nullable=True, comment='Reason this record requires reporting review.')
    source = Column(String(32), nullable=False, comment='Record provenance, such as reconciliation or historical backfill.')
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), comment='UTC timestamp when the ledger record was created.')
