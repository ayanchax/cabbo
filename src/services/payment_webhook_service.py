"""Durable webhook inbox and retries, independent of any provider payload format."""
from datetime import datetime, timedelta, timezone
import logging

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from core.config import settings
from db.database import AsyncSessionLocal
from models.financial.payment_webhook_orm import PaymentWebhookEvent
from models.financial.payments_enum import ReconciliationStateEnum
from models.financial.payments_schema import PaymentWebhookNotice
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_orm import Trip
from services.trips.reconciliation_service import a_reconcile_booking
from sqlalchemy.ext.asyncio import AsyncSession
from utils.retry import get_retry_delay_seconds

log = logging.getLogger(__name__)

_EVENT_ID_MAX_LENGTH = 255
_WEBHOOK_CLAIM_NEXT_ATTEMPT_AFTER_MINUTES=15
_DEFAULT_PAYMENT_WEBHOOK_BATCH_SIZE=settings.RECONCILE_BATCH_SIZE

async def a_store_payment_webhook(notice: PaymentWebhookNotice, event_id: str, body_hash: str, db:AsyncSession):
    """Acknowledge only after a verified notice is committed to the durable inbox."""
    if not event_id or len(event_id) > _EVENT_ID_MAX_LENGTH:
        raise HTTPException(status_code=400, detail="Missing or invalid webhook event ID")
    key = {"provider": notice.provider, "event_id": event_id}
    existing = await db.get(PaymentWebhookEvent, key)
    if existing is None:
        db.add(PaymentWebhookEvent(**key, event_type=notice.event_type,
                                  order_id=notice.order_id, payment_id=notice.payment_id, body_hash=body_hash))
        try:
            await db.commit()
            return
        except IntegrityError:
            await db.rollback()  # A concurrent delivery may have committed first, perhaps from the scheduler or UI flow.
            existing = await db.get(PaymentWebhookEvent, key)
            if existing is None:
                raise
    if (existing.body_hash != body_hash or existing.order_id != notice.order_id
            or existing.payment_id != notice.payment_id or existing.event_type != notice.event_type):
        raise HTTPException(status_code=400, detail="Webhook event ID conflicts with an existing event")


async def _claim_payment_webhooks(db:AsyncSession, batch_size=_DEFAULT_PAYMENT_WEBHOOK_BATCH_SIZE, event_id=None):
    now = datetime.now(timezone.utc)
    query = select(PaymentWebhookEvent).where(
        PaymentWebhookEvent.provider == settings.PAYMENT_PROVIDER,
        PaymentWebhookEvent.processed_at.is_(None),
        PaymentWebhookEvent.next_attempt_at <= now,
    )
    if event_id:
        query = query.where(PaymentWebhookEvent.event_id == event_id)
    result = await db.execute(
        query.order_by(PaymentWebhookEvent.next_attempt_at, PaymentWebhookEvent.created_at)
        .limit(batch_size).with_for_update(skip_locked=True)
    )
    claimed = []
    for event in result.scalars().all():
        event.attempts += 1
        event.next_attempt_at = now + timedelta(minutes=_WEBHOOK_CLAIM_NEXT_ATTEMPT_AFTER_MINUTES)
        claimed.append((getattr(event.provider, "value", event.provider), event.event_id, event.order_id))
    await db.commit()
    return claimed


async def a_process_payment_webhooks(session_factory=AsyncSessionLocal, *, event_id=None, batch_size=_DEFAULT_PAYMENT_WEBHOOK_BATCH_SIZE):
    """Fast-path background delivery and scheduled retry both drain the same inbox - TempTrips->Trips table."""
    claimed=[]
    try:
        async with session_factory() as db:
            claimed = await _claim_payment_webhooks(db, batch_size, event_id)
    except Exception:
        log.exception("Could not claim payment webhook events")
        return
    for provider, identifier, order_id in claimed:
        state = None
        async with session_factory() as db:
            try:
                order_key = f"{provider}_order_id"
                result = await db.execute(select(TempTrip).where(
                    TempTrip.payment_provider_metadata[order_key].as_string() == order_id))
                temp_trip = result.scalars().first()
                if temp_trip:
                    outcome = await a_reconcile_booking(temp_trip.id, temp_trip.creator_id, db, force_provider_check=True)
                    state = outcome.state
                else:
                    result = await db.execute(select(Trip.id).where(
                        Trip.payment_provider_metadata[order_key].as_string() == order_id))
                    if result.scalars().first():
                        state = ReconciliationStateEnum.booked
                    else:
                        log.warning("Webhook order has no booking association: event %s", identifier)
            except Exception:
                await db.rollback()
                log.exception("Payment webhook reconciliation pending: event %s", identifier)
            try:
                result = await db.execute(select(PaymentWebhookEvent).where(
                    PaymentWebhookEvent.provider == provider, PaymentWebhookEvent.event_id == identifier,
                ).with_for_update().execution_options(populate_existing=True))
                event = result.scalars().first()
                if event and event.processed_at is None:
                    if state in (ReconciliationStateEnum.booked, ReconciliationStateEnum.review_required):
                        event.processed_at = datetime.now(timezone.utc)
                    else:
                            #60 is the initial delay.
                            # 2 doubles it per attempt.
                            # max(..., 0) prevents a negative exponent.
                            # 4 caps the exponent before calculating the power.
                            # 900 caps the resulting delay at 15 minutes.
                        delay = get_retry_delay_seconds(event.attempts)
                        event.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
                    await db.commit()
            except Exception:
                await db.rollback()
                log.exception("Could not update payment webhook event %s", identifier)
    if not claimed or len(claimed)==0:
        log.info("No claimed webhook events picked in this run.")
