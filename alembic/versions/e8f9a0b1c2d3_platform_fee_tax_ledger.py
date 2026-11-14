"""Add platform-fee ledger and invoice identity. No backfill or invoice generation."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import CHAR

revision = "e8f9a0b1c2d3"
down_revision = "d7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("invoices",
        sa.Column('id', CHAR(36), primary_key=True, comment='Stable internal invoice identifier.'),
        sa.Column('entity_id', CHAR(36), sa.ForeignKey('trips.id'), nullable=False, comment='Trip for which this invoice was issued.'),
        sa.Column('invoice_number', sa.String(64), nullable=False, unique=True, comment='Unique customer-facing invoice number.'),
        sa.Column('invoice_date', sa.Date, nullable=False, comment='Legal issue date of the invoice.'),
        sa.Column('s3_object_key', sa.String(1024), nullable=True, comment='Persistent private PDF object key; never an expiring presigned URL.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='UTC timestamp when this invoice record was created.'),
    )
    op.create_table("platform_fee_collections",
        sa.Column('id', CHAR(36), primary_key=True, comment='Stable internal ledger record identifier.'),
        sa.Column('entity_id', CHAR(36), sa.ForeignKey('trips.id'), nullable=False, comment='Trip reference, matching the entity_id used by refunds.'),
        sa.Column('provider', sa.String(32), nullable=False, comment='Payment provider identifier, for example razorpay.'),
        sa.Column('payment_id', sa.String(64), nullable=False, comment='Captured provider payment identifier; unique together with provider.'),
        sa.Column('order_id', sa.String(255), nullable=False, comment='Provider order associated with the captured payment.'),
        sa.Column('payment_status', sa.String(32), nullable=False, comment='Verified provider payment status at collection capture.'),
        sa.Column('currency', sa.String(3), nullable=False, comment='ISO 4217 currency code; monetary values use major currency units.'),
        sa.Column('captured_amount', sa.Numeric(18, 2), nullable=False, comment='Total payment amount captured by the provider, before gateway deductions.'),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True, comment='Provider capture timestamp when available; never substitute verification time.'),
        sa.Column('base_fare', sa.Numeric(18, 2), nullable=True, comment='Historical trip base fare reference; not platform-fee revenue.'),
        sa.Column('platform_fee_base', sa.Numeric(18, 2), nullable=True, comment='Taxable fee base excluding GST; null for unresolved historical breakdowns.'),
        sa.Column('platform_fee_tax', sa.Numeric(18, 2), nullable=True, comment='Actual GST charged; null for unresolved historical breakdowns.'),
        sa.Column('platform_fee_gross', sa.Numeric(18, 2), nullable=False, comment='Platform-fee base plus GST actually charged.'),
        sa.Column('tax_configuration_id', CHAR(36), sa.ForeignKey('tax_configurations.id'), nullable=True, comment='Tax configuration applied at charge time; historical values remain snapshotted.'),
        sa.Column('tax_type', sa.String(32), nullable=True, comment='Tax family applied at charge time, for example GST.'),
        sa.Column('tax_rate_percent', sa.Numeric(7, 4), nullable=True, comment='Historical tax percentage applied to the fee base.'),
        sa.Column('cgst_amount', sa.Numeric(18, 2), nullable=True, comment='Central GST amount; null when allocation is unresolved.'),
        sa.Column('sgst_amount', sa.Numeric(18, 2), nullable=True, comment='State GST amount; null when allocation is unresolved.'),
        sa.Column('igst_amount', sa.Numeric(18, 2), nullable=True, comment='Integrated GST amount; null when allocation is unresolved.'),
        sa.Column('supplier_state_code', sa.String(2), nullable=True, comment='Two-digit GST state code of the supplier.'),
        sa.Column('place_of_supply_state_code', sa.String(2), nullable=True, comment='Two-digit GST state code for the determined place of supply.'),
        sa.Column('customer_id', CHAR(36), nullable=True, comment='Historical customer identifier associated with the collection.'),
        sa.Column('customer_gstin', sa.String(15), nullable=True, comment='Customer GSTIN snapshot, when supplied.'),
        sa.Column('customer_billing_state_code', sa.String(2), nullable=True, comment='Customer billing GST state code snapshot, when available.'),
        sa.Column('reporting_date', sa.Date, nullable=True, comment='Applicable tax reporting date; independent of cash movement and nullable pending review.'),
        sa.Column('review_required', sa.Boolean, nullable=False, server_default='1', comment='Whether unresolved data or tax treatment requires review before filing.'),
        sa.Column('review_reason', sa.String(255), nullable=True, comment='Reason this record requires reporting review.'),
        sa.Column('invoice_id', CHAR(36), sa.ForeignKey('invoices.id'), nullable=True, comment='Final invoice foreign key; null until an invoice is issued.'),
        sa.Column('receipt_reference', sa.String(64), nullable=True, comment='Advance receipt document reference, where applicable.'),
        sa.Column('refund_status', sa.String(32), nullable=False, server_default='unrefunded', comment='Derived collection summary: unrefunded, partially_refunded or fully_refunded.'),
        sa.Column('refunded_base', sa.Numeric(18, 2), nullable=False, server_default='0', comment='Cumulative successfully refunded taxable fee base; adjustment rows store individual refunds.'),
        sa.Column('refunded_tax', sa.Numeric(18, 2), nullable=False, server_default='0', comment='Cumulative successfully refunded GST; adjustment rows store individual refunds.'),
        sa.Column('refunded_gross', sa.Numeric(18, 2), nullable=False, server_default='0', comment='Cumulative successfully refunded gross platform fee.'),
        sa.Column('source', sa.String(32), nullable=False, comment='Record provenance, such as reconciliation or historical backfill.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='UTC timestamp when the ledger record was created.'),
        sa.UniqueConstraint('provider', 'payment_id', name='uq_platform_fee_collection_payment'),
    )
    op.create_index('ix_platform_fee_collection_captured', 'platform_fee_collections', ['captured_at'])
    op.create_index('ix_platform_fee_collection_reporting', 'platform_fee_collections', ['reporting_date'])
    op.create_index('ix_platform_fee_collection_entity', 'platform_fee_collections', ['entity_id'])
    op.create_table("platform_fee_refund_adjustments",
        sa.Column('id', CHAR(36), primary_key=True, comment='Stable internal ledger record identifier.'),
        sa.Column('collection_id', CHAR(36), sa.ForeignKey('platform_fee_collections.id'), nullable=False, comment='Original captured collection being adjusted.'),
        sa.Column('entity_id', CHAR(36), sa.ForeignKey('trips.id'), nullable=False, comment='Trip reference, matching the entity_id used by refunds.'),
        sa.Column('refund_id', CHAR(36), sa.ForeignKey('refunds.id'), nullable=False, comment='Existing refunds table primary key for this successful adjustment.'),
        sa.Column('provider', sa.String(32), nullable=False, comment='Payment provider identifier, for example razorpay.'),
        sa.Column('provider_refund_id', sa.String(64), nullable=False, comment='Successful provider refund identifier; unique together with provider.'),
        sa.Column('currency', sa.String(3), nullable=False, comment='ISO 4217 currency code; monetary values use major currency units.'),
        sa.Column('refunded_base', sa.Numeric(18, 2), nullable=True, comment='Taxable fee base reversed by this refund; null when allocation is unresolved.'),
        sa.Column('refunded_tax', sa.Numeric(18, 2), nullable=True, comment='GST reversed by this refund; null when allocation is unresolved.'),
        sa.Column('refunded_gross', sa.Numeric(18, 2), nullable=False, comment='Gross platform-fee amount reversed by this successful refund.'),
        sa.Column('cgst_amount', sa.Numeric(18, 2), nullable=True, comment='Central GST amount; null when allocation is unresolved.'),
        sa.Column('sgst_amount', sa.Numeric(18, 2), nullable=True, comment='State GST amount; null when allocation is unresolved.'),
        sa.Column('igst_amount', sa.Numeric(18, 2), nullable=True, comment='Integrated GST amount; null when allocation is unresolved.'),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=False, comment='UTC provider refund completion timestamp; does not determine GST reporting date.'),
        sa.Column('reporting_date', sa.Date, nullable=True, comment='Applicable tax reporting date; independent of cash movement and nullable pending review.'),
        sa.Column('document_type', sa.String(32), nullable=True, comment='Adjustment document kind, such as credit_note or refund_voucher.'),
        sa.Column('document_number', sa.String(64), nullable=True, comment='Adjustment document number, when issued.'),
        sa.Column('document_date', sa.Date, nullable=True, comment='Adjustment document issue date, independent of provider processing.'),
        sa.Column('review_required', sa.Boolean, nullable=False, server_default='1', comment='Whether unresolved data or tax treatment requires review before filing.'),
        sa.Column('review_reason', sa.String(255), nullable=True, comment='Reason this record requires reporting review.'),
        sa.Column('source', sa.String(32), nullable=False, comment='Record provenance, such as reconciliation or historical backfill.'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, comment='UTC timestamp when the ledger record was created.'),
        sa.UniqueConstraint('provider', 'provider_refund_id', name='uq_platform_fee_adjustment_provider_refund'),
        sa.UniqueConstraint('refund_id', name='uq_platform_fee_adjustment_refund'),
    )
    op.create_index('ix_platform_fee_adjustment_collection', 'platform_fee_refund_adjustments', ['collection_id'])
    op.create_index('ix_platform_fee_adjustment_processed', 'platform_fee_refund_adjustments', ['processed_at'])
    op.create_index('ix_platform_fee_adjustment_reporting', 'platform_fee_refund_adjustments', ['reporting_date'])


def downgrade():
    op.drop_table("platform_fee_refund_adjustments")
    op.drop_table("platform_fee_collections")
    op.drop_table("invoices")
