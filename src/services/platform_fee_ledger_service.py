"""Persist verified collections without provider calls or transaction ownership."""
import logging

from sqlalchemy import select, or_
from decimal import Decimal, ROUND_HALF_UP
from models.financial.payments_enum import ReconciliationStateEnum
from models.financial.platform_fee_ledger_orm import PlatformFeeCollection, PlatformFeeRefundAdjustment
from models.policies.refund_enum import RefundStatus
from models.policies.refund_orm import Refund
from models.trip.trip_orm import Trip
from sqlalchemy.ext.asyncio import AsyncSession

from utils.money import MONEY_PRECISION, to_decimal
log = logging.getLogger(__name__)


async def a_ensure_platform_fee_collection(trip:Trip, db:AsyncSession, source:str="reconciliation") -> PlatformFeeCollection | None:
    """Caller holds the trip row lock and commits this entry with booking changes.

    Verification paths match the provider amount/currency to the stored charge.
    Never use current tax configuration or trip-completion dates for history.
    """
    metadata = trip.payment_provider_metadata or {}
    provider = getattr(trip.payment_provider, "value", trip.payment_provider)
    payment_id = metadata.get(f"{provider}_payment_id")
    order_id = trip.payment_order_id
    if not provider or not payment_id or not order_id:
        log.warning("Ledger capture evidence incomplete for trip %s", trip.id)
        return None
    result = await db.execute(select(PlatformFeeCollection).where(
        PlatformFeeCollection.provider == provider,
        PlatformFeeCollection.payment_id == payment_id,
    ))
    existing = result.scalars().first()
    if existing:
        if existing.entity_id != trip.id or existing.order_id != order_id:
            raise ValueError("Ledger payment already belongs to another booking")
        return existing
    if metadata.get("payment_verified") is not True:
        log.warning("Ledger capture not verified for trip %s", trip.id)
        return None
    gross = to_decimal(trip.advance_payment)
    currency = metadata.get("currency")
    if gross is None or gross <= 0 or not currency:
        log.warning("Ledger charge evidence incomplete for trip %s", trip.id)
        return None
    breakdown = trip.price_breakdown or {}
    
    base = to_decimal(breakdown.get("platform_fee_base"))
    tax = to_decimal(breakdown.get("platform_fee_tax"))
    rate = to_decimal(breakdown.get("platform_fee_tax_rate_percent"))
    # These reporting details are not established by the current capture flow.
    # Keep explicit reasons until capture evidence and GST reporting rules resolve them.
    reasons = ["capture_timestamp_unavailable", "tax_jurisdiction_unconfirmed", "reporting_period_unconfirmed"]
    if base is None or tax is None or base + tax != gross:
        # Retain the known collection without guessing a tax-exclusive amount.
        base = tax = None
        reasons.append("tax_breakdown_unresolved")
    collection = PlatformFeeCollection(
        entity_id=trip.id, provider=provider, payment_id=payment_id,
        order_id=order_id, payment_status=ReconciliationStateEnum.captured.value, currency=currency,
        captured_amount=gross.quantize(MONEY_PRECISION),
        platform_fee_gross=gross.quantize(MONEY_PRECISION),
        platform_fee_base=base, 
        platform_fee_tax=tax,
        base_fare=to_decimal(breakdown.get("base_fare")),
        tax_rate_percent=rate, 
        tax_type=breakdown.get("platform_fee_tax_type", "GST"),
        # A configuration ID is linked only when persisted in the charge snapshot.
        tax_configuration_id=breakdown.get("platform_fee_tax_configuration_id"),
        customer_id=trip.creator_id, 
        source=source,
        # GST filing readiness only; this does not hold booking/refund processing.
        # Currently always true because the reporting reasons above are unresolved.
        # Once those are evaluated individually, derive this flag from bool(reasons).
        review_required=bool(reasons), review_reason=",".join(reasons),
    )
    db.add(collection)
    await db.flush()
    return collection


async def a_record_platform_fee_refund(refund:Refund, trip:Trip, db:AsyncSession, source:str = "refund_worker") -> PlatformFeeRefundAdjustment | None:
    """Append a successful cash refund and update totals in the caller's transaction.

    Lock the original collection to serialize different refunds of one payment.
    GST reporting remains on review; cash allocation does not issue a credit note.
    """
    if refund.refund_status not in (RefundStatus.processed, RefundStatus.completed):
        return None
    provider = getattr(refund.refund_provider, "value", refund.refund_provider)
    if trip is None or trip.id != refund.entity_id or not refund.provider_refund_id or not refund.payment_id:
        raise ValueError("Successful refund is missing ledger identity evidence")
    collection = await a_ensure_platform_fee_collection(trip, db, source=source)
    if collection is None:
        raise ValueError("Successful refund has no verified collection snapshot")
    result = await db.execute(select(PlatformFeeCollection).where(
        PlatformFeeCollection.id == collection.id,
    ).with_for_update().execution_options(populate_existing=True))
    collection = result.scalars().one()
    details = refund.refund_details or {}
    currency = details.get("_currency_code") or details.get("currency")
    amount = to_decimal(refund.refund_amount)
    if (collection.provider != provider or collection.payment_id != refund.payment_id
            or currency != collection.currency or amount is None or amount <= 0
            or amount != amount.quantize(MONEY_PRECISION)):
        raise ValueError("Refund does not match the original collection")
    result = await db.execute(select(PlatformFeeRefundAdjustment).where(or_(
        PlatformFeeRefundAdjustment.refund_id == refund.id,
        (PlatformFeeRefundAdjustment.provider == provider)
        & (PlatformFeeRefundAdjustment.provider_refund_id == refund.provider_refund_id),
    )))
    existing = result.scalars().first()
    if existing:
        if (existing.collection_id != collection.id or existing.refund_id != refund.id
                or existing.provider_refund_id != refund.provider_refund_id
                or existing.refunded_gross != amount or existing.currency != currency):
            raise ValueError("Existing refund adjustment conflicts with provider evidence")
        return existing
    result = await db.execute(select(PlatformFeeRefundAdjustment).where(
        PlatformFeeRefundAdjustment.collection_id == collection.id,
    ))
    previous = result.scalars().all()
    previous_gross = sum((row.refunded_gross for row in previous), Decimal(0))
    total_gross = previous_gross + amount
    if total_gross > collection.platform_fee_gross:
        raise ValueError("Refund adjustments exceed the original platform fee")
    reasons = ["tax_jurisdiction_unconfirmed", "reporting_period_unconfirmed", "refund_document_unconfirmed",
               "refund_processed_timestamp_unavailable"]
    base = tax = None
    known_breakdown = (collection.platform_fee_base is not None and collection.platform_fee_tax is not None
                       and collection.platform_fee_base + collection.platform_fee_tax == collection.platform_fee_gross
                       and all(row.refunded_base is not None and row.refunded_tax is not None for row in previous))
    if known_breakdown:
        previous_base = sum((row.refunded_base for row in previous), Decimal(0))
        previous_tax = sum((row.refunded_tax for row in previous), Decimal(0))
        # Allocate against the original charged amounts. The final refund takes
        # the remainder, preventing accumulated paise rounding discrepancies.
        target_base = (collection.platform_fee_base if total_gross == collection.platform_fee_gross else
                       (total_gross * collection.platform_fee_base / collection.platform_fee_gross)
                       .quantize(MONEY_PRECISION, rounding=ROUND_HALF_UP))
        base = target_base - previous_base
        tax = total_gross - target_base - previous_tax
        if base < 0 or tax < 0:
            raise ValueError("Historical refund allocation requires review")
    else:
        reasons.append("tax_breakdown_unresolved")
    adjustment = PlatformFeeRefundAdjustment(
        collection_id=collection.id, entity_id=trip.id, refund_id=refund.id,
        provider=provider, provider_refund_id=refund.provider_refund_id, currency=currency,
        refunded_gross=amount, refunded_base=base, refunded_tax=tax,
        # Razorpay refund created_at is submission time, not completion time.
        # Retain unknown completion time rather than inventing a provider date.
        processed_at=None, source=source, review_required=True,
        review_reason=",".join(reasons),
    )
    db.add(adjustment)
    collection.refunded_gross = total_gross
    collection.refunded_base = (previous_base + base) if known_breakdown else None
    collection.refunded_tax = (previous_tax + tax) if known_breakdown else None
    collection.refund_status = ("fully_refunded" if total_gross == collection.platform_fee_gross else "partially_refunded")
    await db.flush()
    return adjustment
