"""Persist verified collections without provider calls or transaction ownership."""
import logging

from sqlalchemy import select
from models.financial.payments_enum import ReconciliationStateEnum
from models.financial.platform_fee_ledger_orm import PlatformFeeCollection
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
