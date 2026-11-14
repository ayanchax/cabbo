"""Payment recovery shared by customer polling, scheduler and webhook"""

from models.financial.payments_schema import ReconciliationOutcome
from models.financial.payments_enum import ReconciliationStateEnum
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.exceptions import CabboException, TRIP_NOT_FOUND
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_orm import Trip
from models.trip.trip_schema import BookingPaymentStatus
from services.configuration_service import get_currency
from services.payment_service import fetch_payment_order_status
from services.platform_fee_ledger_service import a_ensure_platform_fee_collection
from services.trips.booking_service import (
    a_create_confirmed_trip_from_temp_trip,
    a_existing_booking,
)
from utils.utility import convert_based_on_currency
from db.database import AsyncSessionLocal

log = logging.getLogger(__name__)
POLL_INTERVAL_SECONDS = 10


def _status_response(temp_trip_id, state: ReconciliationStateEnum = ReconciliationStateEnum.checking, trip:Trip=None, *, metadata=None) -> BookingPaymentStatus:
    metadata = metadata or {}
    can_retry = False
    if (not trip and state == ReconciliationStateEnum.checking
            and metadata.get("reconciliation_state") == ReconciliationStateEnum.checking
            and metadata.get("can_retry_payment") is True
            and not metadata.get("payment_verified")):
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(metadata["reconciliation_checked_at"])).total_seconds()
            can_retry = 0 <= age < POLL_INTERVAL_SECONDS

        except (KeyError, TypeError, ValueError):
            pass
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
        can_retry_payment=can_retry,
        message=("You can resume payment using your existing order." if can_retry
                 else messages[ReconciliationStateEnum.booked if trip else state]),
    )


async def a_get_booking_payment_status(temp_trip_id: str, requestor: str, db: AsyncSession, check_payment_status: bool = False) -> BookingPaymentStatus:
    """Read stored status by default; optionally await throttled reconciliation."""
    if check_payment_status:
        return await a_reconcile_booking(temp_trip_id, requestor, db)
    result = await db.execute(select(TempTrip).where(
        TempTrip.id == temp_trip_id, TempTrip.creator_id == requestor,
    ))
    temp_trip = result.scalars().first()
    metadata = (temp_trip.payment_provider_metadata or {}) if temp_trip else {}
    order_id = metadata.get(f"{settings.PAYMENT_PROVIDER}_order_id")
    identity = Trip.id == temp_trip_id
    if order_id:
        identity = or_(identity, and_(Trip.payment_provider == settings.PAYMENT_PROVIDER, Trip.payment_order_id == order_id))
    result = await db.execute(select(Trip).where(identity, Trip.creator_id == requestor))
    existing = result.scalars().first()
    if existing:
        return _status_response(temp_trip_id, trip=existing)
    if temp_trip is None:
        raise CabboException("Booking not found", status_code=404, error_code=TRIP_NOT_FOUND)
    state = (ReconciliationStateEnum.review_required
             if metadata.get("reconciliation_state") == ReconciliationStateEnum.review_required.value
             else ReconciliationStateEnum.checking)
    return _status_response(temp_trip_id, state, metadata=metadata)


async def a_request_booking_reconciliation(temp_trip_id: str, requestor: str, db: AsyncSession) -> BookingPaymentStatus:
    """Durably queue an owned booking; repeated requests preserve a pending request."""
    result = await db.execute(select(TempTrip).where(
        TempTrip.id == temp_trip_id, TempTrip.creator_id == requestor,
    ).with_for_update().execution_options(populate_existing=True))
    temp_trip = result.scalars().first()
    metadata = dict(temp_trip.payment_provider_metadata or {}) if temp_trip else {}
    order_id = metadata.get(f"{settings.PAYMENT_PROVIDER}_order_id")
    existing = await a_existing_booking(temp_trip_id, requestor, db, order_id)
    if existing:
        await a_ensure_platform_fee_collection(existing, db)
        response = _status_response(temp_trip_id, trip=existing)
        await db.commit()
        return response
    if temp_trip is None:
        raise CabboException("Booking not found", status_code=404, error_code=TRIP_NOT_FOUND)
    if metadata.get("reconciliation_state") == ReconciliationStateEnum.review_required:
        await db.commit()
        return _status_response(temp_trip_id, ReconciliationStateEnum.review_required)
    if not order_id:
        raise CabboException("Booking has no payment order", status_code=409, error_code=TRIP_NOT_FOUND)
    if not metadata.get("reconciliation_request_pending"):
        now = datetime.now(timezone.utc)
        requested_at = metadata.get("reconciliation_requested_at")
        try:
            recent_request = requested_at and 0 <= (now - datetime.fromisoformat(requested_at)).total_seconds() < POLL_INTERVAL_SECONDS
        except (TypeError, ValueError):
            recent_request = False
        if not recent_request:
            metadata.update(
                reconciliation_request_pending=True,
                reconciliation_requested_at=now.isoformat(),
            )
            # Leave any active scheduler lease intact. Pending requests are also
            # selected explicitly, so queueing never depends on browser survival.
            temp_trip.payment_provider_metadata = metadata
    await db.commit()
    return _status_response(temp_trip_id)


async def a_process_booking_reconciliation_request(temp_trip_id: str, requestor: str, session_factory=AsyncSessionLocal):
    """Best-effort fast path; scheduler recovers the persisted request after a crash."""
    async with session_factory() as db:
        try:
            result = await db.execute(select(TempTrip).where(
                TempTrip.id == temp_trip_id, TempTrip.creator_id == requestor,
            ).with_for_update().execution_options(populate_existing=True))
            temp_trip = result.scalars().first()
            if temp_trip is None or not (temp_trip.payment_provider_metadata or {}).get("reconciliation_request_pending"):
                return
            await a_reconcile_booking(temp_trip_id, requestor, db)
        except Exception:
            await db.rollback()
            log.exception("Requested reconciliation pending for booking %s", temp_trip_id)


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
        await a_ensure_platform_fee_collection(existing, db)
        response = _status_response(temp_trip_id, trip=existing)
        await db.commit()
        return response
    if not temp_trip:
        raise CabboException("Booking not found", status_code=404, error_code=TRIP_NOT_FOUND)
    expired_review = metadata.get("reconciliation_reason") in (
        "automatic_reconciliation_expired", "automatic_reconciliation_unavailable",
    )
    if (metadata.get("reconciliation_state") == ReconciliationStateEnum.review_required
            and not (expired_review and (force_provider_check or actor_id))):
        await db.commit()
        return _status_response(temp_trip_id, ReconciliationStateEnum.review_required)
    now = datetime.now(timezone.utc)
    checked_at = metadata.get("reconciliation_checked_at")
    if checked_at and not force_provider_check and not actor_id:
        try:
#             Prevents checking the payment provider too frequently.
#             It converts the stored last-check timestamp into a datetime.
#             If the last check was less than 10 seconds ago, it returns “checking” without calling the provider again.
#             db.commit() ends the transaction and releases the row lock.
#             If the timestamp is missing or malformed, reconciliation proceeds with a fresh provider check.
            checked = datetime.fromisoformat(checked_at)
            if 0 <= (now - checked).total_seconds() < POLL_INTERVAL_SECONDS:
                await db.commit()
                return _status_response(temp_trip_id, metadata=metadata)
        except (TypeError, ValueError):
            pass
    metadata["reconciliation_checked_at"] = now.isoformat()
    if metadata.get("reconciliation_request_pending"):
        # An immediate customer check must not leave unresolved payment behind
        # an older scheduler backoff. Continue on the next scheduled run.
        metadata["reconciliation_next_check_at"] = now.isoformat()
    metadata["reconciliation_request_pending"] = False
    if actor_id:
        metadata["reconciliation_requested_by"] = actor_id
    outcome = ReconciliationOutcome()
    provider_checked = False
    if order_id:
        currency = get_currency()
        expected_amount = int(convert_based_on_currency(temp_trip.platform_fee, currency.lowest_unit_conversion_factor))
        try:
            outcome = await asyncio.to_thread(fetch_payment_order_status, order_id, expected_amount, currency.code)
            provider_checked = True
        except Exception:
            # Do not expose provider responses, credentials or customer payment details.
            log.warning("Provider check unavailable for temporary booking %s", temp_trip_id)
    state = outcome.state
    # Check provider truth one last time before ending automatic polling. Age
    # alone never means payment failure, and payment evidence must be retained.
    created_at = temp_trip.created_at
    age_hours = (now - created_at.replace(tzinfo=created_at.tzinfo or timezone.utc)).total_seconds() / 3600
    if (order_id and state == ReconciliationStateEnum.checking
            and age_hours >= settings.RECONCILE_ACTIVE_WINDOW_HOURS
            and not metadata.get("payment_verified")
            and metadata.get("reconciliation_state") != ReconciliationStateEnum.captured
            and not metadata.get(f"{settings.PAYMENT_PROVIDER}_payment_id")):
        state = ReconciliationStateEnum.review_required
        outcome.reason = ("automatic_reconciliation_expired" if provider_checked
                          else "automatic_reconciliation_unavailable")
        metadata["reconciliation_polling_stopped_at"] = now.isoformat()
        log.warning("Automatic payment reconciliation ended for temporary booking %s: %s. If the customer has paid, please review the evidence and confirm the booking from admin operations console.",
                    temp_trip_id, outcome.reason)
    metadata["reconciliation_state"] = state
    if expired_review and state != ReconciliationStateEnum.review_required:
        metadata.pop("reconciliation_reason", None)
        metadata.pop("reconciliation_polling_stopped_at", None)
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
            log.error("Captured payment requires backend fulfilment review for temporary booking %s", temp_trip_id)
    start = temp_trip.start_datetime
    metadata["can_retry_payment"] = bool(
        provider_checked and outcome.can_retry_payment
        and state == ReconciliationStateEnum.checking
        and age_hours < settings.RECONCILE_ACTIVE_WINDOW_HOURS
        and not metadata.get("payment_verified")
        and not metadata.get(f"{settings.PAYMENT_PROVIDER}_payment_id")
        and start is not None
        and start.replace(tzinfo=start.tzinfo or timezone.utc) > now
    )
    temp_trip.payment_provider_metadata = metadata
    # Persist evidence first; a failed finalisation remains recoverable.
    await db.commit()
    if state != ReconciliationStateEnum.captured:
        return _status_response(temp_trip_id, state, metadata=metadata)
    try:
        #At this point, since payment status is verified as captured, we can move the temp trip to final trip table with status as confirmed.
        # PAYMENT VERIFIED VIA RECONCIALITAION - TempTrip is hence ELIGIBLE TO MOVE TO `Trips` table as confirmed booking.
        trip = await a_create_confirmed_trip_from_temp_trip(
            temp_trip=temp_trip, requestor=actor_id or requestor, payment_info=payment_info, db=db,
            audit_reason="Booking confirmed by payment reconciliation",
        )
        return _status_response(temp_trip_id, trip=trip)
    except Exception:
        await db.rollback()
        # A response/read error can follow an already committed booking.
        existing = await a_existing_booking(temp_trip_id, requestor, db, order_id)
        if existing:
            await a_ensure_platform_fee_collection(existing, db)
            response = _status_response(temp_trip_id, trip=existing)
            await db.commit()
            return response
        log.exception("Booking confirmation pending after reconciliation for %s", temp_trip_id)
        return _status_response(temp_trip_id)


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
