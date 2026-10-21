from models.financial.payments_schema import ReconciliationOutcome
"""Payment recovery shared by customer polling and future scheduled/webhook work."""
from models.financial.payments_enum import ReconciliationStateEnum
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import CabboException, TRIP_NOT_FOUND
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_orm import Trip
from models.trip.trip_schema import BookingPaymentStatus
from services.configuration_service import get_currency
from services.payment_service import fetch_payment_order_status
from services.trips.booking_service import (
    a_create_confirmed_trip_from_temp_trip,
    a_existing_booking,
)
from utils.utility import convert_based_on_currency

log = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 10


def status_response(temp_trip_id, state: ReconciliationStateEnum = ReconciliationStateEnum.checking, trip:Trip=None) -> BookingPaymentStatus:
    messages = {
        ReconciliationStateEnum.checking: "We're checking your payment. Please don't pay again yet.",
        ReconciliationStateEnum.booked: "Your booking is available in your trips.",
        ReconciliationStateEnum.review_required: "Your booking needs review. Please contact support before paying again.",
    }
    return BookingPaymentStatus(
        temp_trip_id=temp_trip_id,
        state=ReconciliationStateEnum.booked if trip else state,
        trip_id=(getattr(trip, "id", None) or trip.trip_id) if trip else None,
        booking_id=trip.booking_id if trip else None,
        trip_status=trip.status if trip else None,
        retry_after_seconds=POLL_INTERVAL_SECONDS if not trip and state == ReconciliationStateEnum.checking else None,
        can_retry_payment=False,
        message=messages[ReconciliationStateEnum.booked if trip else state],
    )


async def a_reconcile_booking(temp_trip_id: str, requestor: str, db: AsyncSession, *, actor_id: str = None, force_provider_check: bool = False) -> BookingPaymentStatus:
    """Only reconcile bookings owned by requestor; provider failures stay unresolved.

    Persisted throttling and a row lock coordinate checks across API workers.
    No automatic refund, capture, or terminal payment-failed decision is made here.
    """
    result = await db.execute(
        select(TempTrip).where(TempTrip.id == temp_trip_id, TempTrip.creator_id == requestor)
        .with_for_update().execution_options(populate_existing=True)
    )
    temp_trip = result.scalars().first()
    metadata = dict(temp_trip.payment_provider_metadata or {}) if temp_trip else {}
    order_id:str = metadata.get(f"{settings.PAYMENT_PROVIDER}_order_id")
    existing = await a_existing_booking(temp_trip_id, requestor, db, order_id)
    if existing:
        response = status_response(temp_trip_id, trip=existing)
        await db.commit()
        return response
    if not temp_trip:
        raise CabboException("Booking not found", status_code=404, error_code=TRIP_NOT_FOUND)
    if metadata.get("reconciliation_state") == ReconciliationStateEnum.review_required:
        await db.commit()
        return status_response(temp_trip_id, ReconciliationStateEnum.review_required)
    now = datetime.now(timezone.utc)
    checked_at = metadata.get("reconciliation_checked_at")
    if checked_at and not force_provider_check:
        try:
#             Prevents checking the payment provider too frequently.
#             It converts the stored last-check timestamp into a datetime.
#             If the last check was less than 10 seconds ago, it returns “checking” without calling the provider again.
#             db.commit() ends the transaction and releases the row lock.
#             If the timestamp is missing or malformed, reconciliation proceeds with a fresh provider check.
            checked = datetime.fromisoformat(checked_at)
            if 0 <= (now - checked).total_seconds() < POLL_INTERVAL_SECONDS:
                await db.commit()
                return status_response(temp_trip_id)
        except (TypeError, ValueError):
            pass
    metadata["reconciliation_checked_at"] = now.isoformat()
    if actor_id:
        metadata["reconciliation_requested_by"] = actor_id
    outcome = ReconciliationOutcome()
    if order_id:
        currency = get_currency()
        expected_amount = int(convert_based_on_currency(temp_trip.platform_fee, currency.lowest_unit_conversion_factor))
        try:
            outcome = await asyncio.to_thread(fetch_payment_order_status, order_id, expected_amount, currency.code)
        except Exception:
            # Do not expose provider responses, credentials or customer payment details.
            log.warning("Provider check unavailable for temporary booking %s", temp_trip_id)
    state = outcome.state
    metadata["reconciliation_state"] = state
    if outcome.reason:
        metadata["reconciliation_reason"] = outcome.reason
    if state == ReconciliationStateEnum.captured:
        payment_info = outcome.payment_info
        metadata.update(payment_info.model_dump(exclude_none=True))
        metadata.update(payment_verified=True, payment_verified_via=f"{settings.PAYMENT_PROVIDER}_reconciliation",
                        payment_verified_at=now.isoformat())
        start = temp_trip.start_datetime
        if start is None or start.replace(tzinfo=start.tzinfo or timezone.utc) <= now:
            state = ReconciliationStateEnum.review_required
            metadata.update(reconciliation_state=state, reconciliation_reason="pickup_time_passed")
            log.error("Captured payment requires fulfilment review for temporary booking %s", temp_trip_id)
    temp_trip.payment_provider_metadata = metadata
    # Persist evidence first; a failed finalisation remains recoverable.
    await db.commit()
    if state != ReconciliationStateEnum.captured:
        return status_response(temp_trip_id, state)
    try:
        trip = await a_create_confirmed_trip_from_temp_trip(
            temp_trip=temp_trip, requestor=actor_id or requestor, payment_info=payment_info, db=db,
            audit_reason="Booking confirmed by payment reconciliation",
        )
        return status_response(temp_trip_id, trip=trip)
    except Exception:
        await db.rollback()
        log.exception("Booking confirmation pending after reconciliation for %s", temp_trip_id)
        return status_response(temp_trip_id)


async def a_reconcile_booking_as_admin(temp_trip_id: str, admin_user_id: str, db: AsyncSession) -> BookingPaymentStatus:
    """Resolve ownership server-side; caller must enforce the admin role check."""
    result = await db.execute(select(TempTrip.creator_id).where(TempTrip.id == temp_trip_id))
    owner_id = result.scalars().first()
    if owner_id is None:
        result = await db.execute(select(Trip.creator_id).where(Trip.id == temp_trip_id))
        owner_id = result.scalars().first()
    if owner_id is None:
        raise CabboException("Booking not found", status_code=404, error_code=TRIP_NOT_FOUND)
    return await a_reconcile_booking(temp_trip_id, owner_id, db, actor_id=admin_user_id)
