"""Durable refund submission, provider reconciliation, and notification retries."""
from core import refund_error_codes as refund_errors
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from core.config import settings
from db.database import ASYNC_DATABASE_URL, ASYNC_CONNECT_ARGS
from models.policies.refund_orm import Refund as RefundORM
from models.policies.refund_enum import RefundStatus
from models.trip.trip_orm import Trip
from models.trip.trip_enums import TripStatusEnum
from scheduler.task_registry import task
from services.payment_service import (
    RefundReviewRequired, RefundRetryableError, get_payment_id_prefix, get_refund_id_prefix, reconcile_or_submit_refund, fetch_refund,
)
from services.refund_service import get_refund_for_processing, send_refund_credited_notification
from services.notification_service import notify_trip_cancellation_to_customer
from utils.money import subunits
from utils.retry import get_retry_delay_seconds

log = logging.getLogger(__name__)
REFUND_POLL_BATCH_SIZE = 50
REFUND_LEASE_MINUTES = 15


@task(task_id="sync_pending_refund_statuses",
      description="Submits queued refunds, reconciles provider status, and retries notifications")
def sync_pending_refund_statuses_task():
    asyncio.run(_run_refund_status_sync())


async def _run_refund_status_sync(session_factory=None):
    # APScheduler creates a new loop each run. Never reuse pooled connections
    # belonging to the API loop or an earlier scheduler invocation.
    engine = None
    if session_factory is None:
        engine = create_async_engine(ASYNC_DATABASE_URL, connect_args=ASYNC_CONNECT_ARGS)
        session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as db:
            claimed = await _fetch_actionable_refunds(db)
        for identifier in claimed:
            # Only scalar IDs cross session boundaries. A rollback cannot expire
            # another refund's loaded relationships or even its logging fields.
            async with session_factory() as db:
                try:
                    refund = await get_refund_for_processing(identifier, db)
                    if refund is None or not refund.is_active:
                        continue # to next eligible claim; the refund may have been deleted or deactivated after the claim.
                    await _process_single_refund(db, refund)
                    # The final allowed attempt still runs. If work remains,
                    # stop automatically without waiting for another claim.
                    if (refund.attempts >= settings.REFUND_MAX_ATTEMPTS
                            and not refund.review_required and not _is_refund_work_complete(refund)):
                        _mark_refund_attempt_limit(refund)
                    await db.commit()
                except Exception:
                    await db.rollback()
                    log.exception("Refund worker failed for intent %s; lease will expire", identifier)
        if not claimed:
            log.info("No due refund work")
        else:
            log.info("Processed %d refund intents", len(claimed))

        next_scheduler_run = datetime.now(timezone.utc) + timedelta(minutes=settings.REFUND_POLL_INTERVAL_MINUTES)
        log.info(f"Next scheduler run: {next_scheduler_run}")

    finally:
        if engine is not None:
            await engine.dispose()


async def _fetch_actionable_refunds(db: AsyncSession) -> list[str]:
    """Commit bounded claims before network I/O; expired leases recover crashes."""
    now = datetime.now(timezone.utc)
    result = await db.execute(select(RefundORM).where(
        RefundORM.is_active.is_(True),
        # Unlike other review reasons, exhausted work cannot be reclaimed even
        # for an outstanding email. Include exhausted non-review rows once so
        # a crash on the final attempt can be converted into durable review.
        or_(RefundORM.attempts < settings.REFUND_MAX_ATTEMPTS,
            RefundORM.review_required.is_(False)),
        # Review holds money operations, not outstanding customer notifications.
        or_(RefundORM.review_required.is_(False),
            and_(RefundORM.cancellation_notified_at.is_(None),
                 or_(RefundORM.refund_details["eligibility_unresolved"].as_boolean().is_(None),
                     RefundORM.refund_details["eligibility_unresolved"].as_boolean().is_(False))),
            and_(RefundORM.refund_status == RefundStatus.processed,
                 RefundORM.processed_notified_at.is_(None))),
        or_(RefundORM.next_attempt_at.is_(None), RefundORM.next_attempt_at <= now),
        or_(RefundORM.refund_status.in_([
            RefundStatus.initiated, RefundStatus.pending, RefundStatus.failed, RefundStatus.unknown,
        ]), RefundORM.refund_status.is_(None), RefundORM.cancellation_notified_at.is_(None),
            and_(RefundORM.refund_status == RefundStatus.processed,
                 RefundORM.processed_notified_at.is_(None))),
    ).order_by(RefundORM.next_attempt_at, RefundORM.created_at, RefundORM.id)
      .limit(REFUND_POLL_BATCH_SIZE).with_for_update(skip_locked=True))
    claimed = []
    for refund in result.scalars().all():
        if (refund.attempts or 0) >= settings.REFUND_MAX_ATTEMPTS:
            _mark_refund_attempt_limit(refund)
            continue
        refund.attempts = (refund.attempts or 0) + 1
        refund.next_attempt_at = now + timedelta(minutes=REFUND_LEASE_MINUTES)
        # Deterministic per obligation, including legacy rows after deployment.
        if not refund.idempotency_key:
            refund.idempotency_key = str(uuid5(NAMESPACE_URL, f"cabbo:refund:{refund.entity_id}"))
        claimed.append(refund.id)
    await db.commit()
    return claimed


def _is_refund_work_complete(refund):
    return (refund.refund_status in (RefundStatus.processed, RefundStatus.completed)
            and refund.cancellation_notified_at is not None
            and (refund.refund_status == RefundStatus.completed
                 or refund.processed_notified_at is not None))


def _mark_refund_attempt_limit(refund):
    """Retain the obligation and original failure evidence for admin review."""
    details = dict(refund.refund_details or {})
    if refund.last_error and refund.last_error != refund_errors.REFUND_MAX_ATTEMPTS_EXCEEDED:
        details["last_error_before_attempt_limit"] = refund.last_error
    refund.refund_details = details
    refund.review_required = True
    refund.last_error = refund_errors.REFUND_MAX_ATTEMPTS_EXCEEDED
    refund.next_attempt_at = None
    log.warning("Refund intent %s reached its %s-attempt limit; admin review required",
                refund.id, settings.REFUND_MAX_ATTEMPTS)


 
async def _process_single_refund(db: AsyncSession, refund: RefundORM):
    """Caller owns the transaction; never refresh/lazy-load after commit here."""
    trip = refund.trip
    now = datetime.now(timezone.utc)
    details = dict(refund.refund_details or {})
    if refund.review_required:
        await _send_notifications(refund, trip)
        refund.next_attempt_at = now + timedelta(seconds=get_retry_delay_seconds(refund.attempts or 1))
        return
    try:
        if trip is None or trip.status != TripStatusEnum.cancelled:
            raise RefundReviewRequired(refund_errors.MISSING_OR_NOT_CANCELLED_TRIP)
        if details.get("eligibility_unresolved"):
            raise RefundReviewRequired(refund_errors.REFUND_ELIGIBILITY_UNRESOLVED)
        if refund.refund_provider != settings.PAYMENT_PROVIDER:
            raise RefundReviewRequired(refund_errors.UNSUPPORTED_REFUND_PROVIDER)
        config = settings.get_config_store().geographies.country_server
        currency = details.get("_currency_code") or details.get("currency") or config.currency
        factor = details.get("_currency_factor") or config.currency_lowest_unit_conversion_factor
        # Snapshot currency so configuration cannot change an idempotent request.
        details.update(_currency_code=currency, _currency_factor=factor)
        refund.refund_details = details
        metadata = trip.payment_provider_metadata or {}
        provider_id = refund.provider_refund_id
        legacy_id = str(details.get("id") or refund.id or "")
        refund_id_prefix = get_refund_id_prefix(provider=refund.refund_provider or settings.PAYMENT_PROVIDER)
        if not provider_id and legacy_id.startswith(refund_id_prefix):
            provider_id = legacy_id
            refund.provider_refund_id = provider_id
        payment_id_prefix = get_payment_id_prefix(provider=refund.refund_provider or settings.PAYMENT_PROVIDER)
        payment_id = (refund.payment_id or details.get("payment_id")
                      or (legacy_id if legacy_id.startswith(payment_id_prefix) else None)
                      or metadata.get(f"{settings.PAYMENT_PROVIDER}_payment_id"))
        if not payment_id:
            raise RefundReviewRequired(refund_errors.MISSING_PAYMENT_ID)
        refund.payment_id = payment_id
        amount = subunits(refund.refund_amount, factor)
        if refund.refund_status not in (RefundStatus.processed, RefundStatus.completed):
            # All provider selection and SDK construction go through the payment
            # service; keep blocking network calls outside this asyncio loop.
            if provider_id:
                response = await asyncio.to_thread(fetch_refund,
                    refund_id=provider_id, payment_id=payment_id, amount=amount, currency=currency,
                    provider=refund.refund_provider)
            else:
                response = await asyncio.to_thread(reconcile_or_submit_refund,
                    payment_id=payment_id, amount=amount,
                    original_amount=subunits(trip.advance_payment, factor),
                    currency=currency, order_id=metadata.get(f"{settings.PAYMENT_PROVIDER}_order_id"),
                    idempotency_key=refund.idempotency_key, entity_id=refund.entity_id,
                    provider=refund.refund_provider)
            refund.provider_refund_id = response["id"]
            refund.refund_status = RefundStatus(response["status"])
            # Public amount remains in standard units, as in the existing API.
            details.update(response, amount=float(Decimal(response["amount"]) / factor))
            refund.refund_retried_datetime = now
        refund.refund_details = details
        refund.last_error = None
        if refund.refund_status == RefundStatus.failed:
            # A known failed provider refund is a financial review case, not
            # permission to create a second refund with a different key.
            refund.review_required = True
            refund.last_error = refund_errors.PROVIDER_REFUND_FAILED
    except RefundReviewRequired as exc:
        refund.review_required = True
        refund.last_error = str(exc)
        log.warning("Refund intent %s requires review: %s", refund.id, exc)
    except Exception as exc:
        # Unknown provider state is not a provider-declared failed refund.
        refund.last_error = (str(exc) if isinstance(exc, RefundRetryableError)
                             else refund_errors.PROVIDER_STATUS_UNAVAILABLE)
        log.warning("Refund intent %s remains retryable: %s", refund.id, refund.last_error)
    # The caller commits financial state even if email fails. No refresh/lazy
    # relationship access after commit, avoiding implicit async ORM I/O.
    await db.flush()
    await _send_notifications(refund, trip)
    refund.next_attempt_at = now + timedelta(seconds=get_retry_delay_seconds(refund.attempts or 1))


async def _send_notifications(refund, trip):
    if not trip or not trip.customer or not trip.customer.email:
        if refund.last_error is None:
            refund.last_error = refund_errors.MISSING_NOTIFICATION_RECIPIENT
        return
    if (refund.refund_details or {}).get("eligibility_unresolved"):
        # The stored amount is provisional; never email a refund promise before
        # finance establishes entitlement under the cancellation policy.
        return
    try:
        config = settings.get_config_store().geographies.country_server
        decimals = config.currency_decimal_places
        if refund.cancellation_notified_at is None:
            sent = await notify_trip_cancellation_to_customer(
                customer=trip.customer, refund_amount=f"{refund.refund_amount:.{decimals}f}",
                refund_type=refund.refund_type, currency=config.currency_symbol,
                booking_id=trip.booking_id, original_amount=f"{trip.advance_payment:.{decimals}f}")
            if not sent:
                raise RuntimeError(refund_errors.CANCELLATION_NOTIFICATION_NOT_DELIVERED)
            refund.cancellation_notified_at = datetime.now(timezone.utc)
        if refund.refund_status == RefundStatus.processed and refund.processed_notified_at is None:
            if not await send_refund_credited_notification(refund, trip, refund.provider_refund_id):
                raise RuntimeError(refund_errors.PROCESSED_NOTIFICATION_NOT_DELIVERED)
            refund.processed_notified_at = datetime.now(timezone.utc)
    except Exception:
        # A crash after send but before commit can repeat an email (at-least-once
        # delivery); notification retries never submit another money refund.
        if refund.last_error is None:
            refund.last_error = refund_errors.NOTIFICATION_DELIVERY_FAILED
        log.exception("Refund notification pending for intent %s", refund.id)


if __name__ == "__main__":
    asyncio.run(_run_refund_status_sync())