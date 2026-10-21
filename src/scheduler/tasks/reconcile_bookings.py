"""Recover paid bookings independently of customer browser activity."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from core.config import settings
from db.database import AsyncSessionLocal, ASYNC_DATABASE_URL, ASYNC_CONNECT_ARGS
from models.financial.payments_enum import ReconciliationStateEnum
from models.trip.temp_trip_orm import TempTrip
from scheduler.task_registry import task
from services.trips.reconciliation_service import a_reconcile_booking

log = logging.getLogger(__name__)
BATCH_SIZE = 20
CLAIM_SECONDS = 900 #15 mins
MAX_BACKOFF_SECONDS = 900


@task(task_id="reconcile_bookings", description="Reconciles unresolved booking payment orders")
def reconcile_bookings_task():
    asyncio.run(_run_scheduled_booking_reconciliation())


async def _run_scheduled_booking_reconciliation():
    # APScheduler uses a new event loop for each run. Never reuse pooled async
    # connections belonging to the API loop or a previous scheduler invocation.
    engine = create_async_engine(ASYNC_DATABASE_URL, connect_args=ASYNC_CONNECT_ARGS)
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        from services.payment_webhook_service import a_process_payment_webhooks
        await a_process_payment_webhooks(session_factory=sessions)
        await _run_booking_reconciliation(session_factory=sessions)
    finally:
        await engine.dispose()


async def _claim_bookings(db, batch_size=BATCH_SIZE):
    """Persist leases before network calls; other scheduler workers skip claimed rows."""
    now = datetime.now(timezone.utc)
    metadata = TempTrip.payment_provider_metadata
    order_id = metadata[f"{settings.PAYMENT_PROVIDER}_order_id"].as_string()
    state = metadata["reconciliation_state"].as_string()
    due = metadata["reconciliation_next_check_at"].as_string()
    result = await db.execute(
        select(TempTrip).where(
            order_id.is_not(None), order_id != "",
            or_(state.is_(None), state.notin_([
                ReconciliationStateEnum.review_required.value, ReconciliationStateEnum.booked.value,
            ])),
            or_(due.is_(None), due <= now.isoformat()),
        ).order_by(due.asc(), TempTrip.created_at.asc(), TempTrip.id.asc())
        .limit(batch_size).with_for_update(skip_locked=True)
        .execution_options(populate_existing=True)
    )
    claimed = []
    for temp_trip in result.scalars().all():
        details = dict(temp_trip.payment_provider_metadata or {})
        details["reconciliation_next_check_at"] = (now + timedelta(seconds=CLAIM_SECONDS)).isoformat()
        temp_trip.payment_provider_metadata = details
        claimed.append((temp_trip.id, temp_trip.creator_id))
    await db.commit()
    return claimed


async def _schedule_next_check(db, temp_trip_id, state=None):
    """Update current metadata under lock without losing concurrent UI reconciliation."""
    result = await db.execute(
        select(TempTrip).where(TempTrip.id == temp_trip_id).with_for_update()
        .execution_options(populate_existing=True)
    )
    temp_trip = result.scalars().first()
    if temp_trip is None:  # Successful finalisation normally consumes the temporary row.
        await db.commit()
        return
    details = dict(temp_trip.payment_provider_metadata or {})
    if state == ReconciliationStateEnum.booked:
        details["reconciliation_state"] = ReconciliationStateEnum.booked.value
    # Cap the exponent as well as the delay for indefinitely abandoned orders.
    try:
        previous_attempts = int(details.get("reconciliation_attempts", 0))
    except (TypeError, ValueError):
        previous_attempts = 0
    attempts = min(max(previous_attempts, 0) + 1, 16)
    delay = min(60 * 2 ** (attempts - 1), MAX_BACKOFF_SECONDS)
    details.update(
        reconciliation_attempts=attempts,
        reconciliation_next_check_at=(datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat(),
    )
    temp_trip.payment_provider_metadata = details
    await db.commit()


async def _run_booking_reconciliation(batch_size=BATCH_SIZE, session_factory=AsyncSessionLocal):
    if not 1 <= batch_size <= BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {BATCH_SIZE}")
    async with session_factory() as db:
        try:
            claimed = await _claim_bookings(db, batch_size) #Claim/pick up unresolved payment linked bookings for reconcialation.
        except Exception:
            await db.rollback()
            log.exception("Could not claim bookings for reconciliation")
            return
    for temp_trip_id, requestor in claimed:
        # Each booking gets its own transaction/session, so one error cannot poison the batch.
        async with session_factory() as db:
            state = None
            try:
                outcome = await a_reconcile_booking(temp_trip_id, requestor, db)
                state = outcome.state
                if state == ReconciliationStateEnum.review_required:
                    log.warning("Booking reconciliation requires operator review: %s", temp_trip_id)
            except Exception:
                await db.rollback()
                log.exception("Scheduled booking reconciliation failed for %s", temp_trip_id)
            try:
                await _schedule_next_check(db, temp_trip_id, state)
            except Exception:
                await db.rollback()
                # The persisted claim expires, allowing recovery even if rescheduling fails.
                log.exception("Could not reschedule booking reconciliation for %s", temp_trip_id)
    log.info("Scheduled booking reconciliation processed %s bookings", len(claimed))
