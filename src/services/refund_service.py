from core import refund_error_codes as refund_errors
from datetime import datetime, timezone
from uuid import uuid4, uuid5, NAMESPACE_URL
from typing import Optional, Union

from core.exceptions import GENERIC_EXCEPTION, TRIP_NOT_FOUND, CabboException
from core.security import RoleEnum
from core.store import ConfigStore
from core.trip_helpers import attach_relationships_to_trip
from models.customer.customer_schema import CustomerPayment, CustomerRead
from models.financial.payments_schema import PaymentNotesSchema
from models.policies.cancelation_schema import CancelationPolicySchema
from models.policies.refund_enum import PaymentProvider, RefundStatus, RefundType
from models.pricing.pricing_schema import Currency
from models.trip.trip_enums import (
    CancellationSubStatusEnum,
    TripResponseView,
    TripStatusEnum,
    TripTypeEnum,
)
from models.trip.trip_orm import Trip
from models.trip.trip_schema import TripDetailSchema
from models.policies.refund_orm import Refund as RefundORM
from models.policies.refund_schema import RefundSchema
from core.config import settings
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from services.cancelation_service import get_cancelation_policy_id
from sqlalchemy.ext.asyncio import AsyncSession

from services.notification_service import notify_refund_processed_to_customer, notify_trip_cancellation_to_customer
from services.payment_service import (
    get_initial_refund_response,
)
import logging


log = logging.getLogger(__name__)


async def get_refund_for_processing(refund_id: str, db: AsyncSession) -> Optional[RefundORM]:
    """Lock the intent and load relationships needed by the async worker.

    The caller owns commit/rollback, keeping this lock through processing.
    Eager loading avoids implicit database I/O when building notifications.
    """
    result = await db.execute(
        select(RefundORM).where(RefundORM.id == refund_id)
        .options(joinedload(RefundORM.trip).joinedload(Trip.customer))
        .with_for_update().execution_options(populate_existing=True)
    )
    return result.scalars().unique().first()


async def refund_advance_payment_to_customer_on_cancellation(
    trip: TripDetailSchema,
    db: AsyncSession,
    cancelation_sub_status: CancellationSubStatusEnum,
    config_store: ConfigStore = None,
    silently_fail: bool = False,
    requestor: str = None,
    commit: bool = True,
):
    try:
        is_existing_refund = await _is_existing_refund(
            id=trip.id, db=db, silently_fail=silently_fail
        )
        if is_existing_refund:
            log.info(
                f"Refund initiation for trip {trip.id} is already in process or completed, hence skipping refund initiation"
            )
            return False

        # Determine if the cancellation is done by cabbo or by driver or due to any other reason except customer cancellation or customer no show, because if the customer is canceling the trip then they should be responsible for any cancellation charges and we should not refund the advance payment in that case or refund partially. But if the trip is canceled by cabbo or by driver admin or due to any other reason except customer cancellation, then we should refund the advance payment to customer in full because it is not the fault of customer and they should not be penalized for that.
        canceled_by_cabbo = cancelation_sub_status not in [
            CancellationSubStatusEnum.customer_cancelled,
            CancellationSubStatusEnum.customer_no_show,
        ]

        if not config_store:
            config_store = settings.get_config_store()

        if trip.advance_payment is None or trip.advance_payment <= 0.0:
            log.info(f"No advance payment to refund for trip {trip.id}")
            return False

        eligible_for_partial_configuration_based_refund = False
        eligible_for_full_refund = False
        refund_amount = 0.0
        cancellation_policy: Optional[CancelationPolicySchema] = None
        if canceled_by_cabbo:
            eligible_for_full_refund = True
            refund_amount = trip.advance_payment
        else:
            # For customer no show cases(reported by driver to driver admin), we will not refund the advance payment as it is the responsibility of customer to cancel the trip in time if they are not going to use it and if they do a no show then it is not the fault of cabbo and hence we should not refund the advance payment in that case.
            if cancelation_sub_status == CancellationSubStatusEnum.customer_no_show:
                log.info(
                    f"Cancellation for trip {trip.id} is marked as customer no-show, hence not eligible for refund"
                )
                return False

            # For other customer-initiated cancellation cases, we will check the cancellation policy based on the trip type and region/state and then determine the refund amount based on the cancellation time and the free cancellation cutoff time defined in the cancellation policy for that trip type and region/state.
            if trip.trip_type_master.trip_type in [
                TripTypeEnum.airport_drop,
                TripTypeEnum.airport_pickup,
                TripTypeEnum.local,
            ]:
                region_code = trip.origin.region_code
                try:
                    if trip.trip_type_master.trip_type == TripTypeEnum.airport_drop:
                        cancellation_policy = config_store.airport_drop.get(
                            region_code
                        ).auxiliary_pricing.cancellation_policy.get(
                            trip.trip_type_master.id
                        )
                    elif trip.trip_type_master.trip_type == TripTypeEnum.airport_pickup:
                        cancellation_policy = config_store.airport_pickup.get(
                            region_code
                        ).auxiliary_pricing.cancellation_policy.get(
                            trip.trip_type_master.id
                        )
                    elif trip.trip_type_master.trip_type == TripTypeEnum.local:
                        cancellation_policy = config_store.local.get(
                            region_code
                        ).auxiliary_pricing.cancellation_policy.get(
                            trip.trip_type_master.id
                        )
                except Exception as e:
                    log.error(
                        f"Error while fetching cancellation policy for trip {trip.id} with region code {region_code} and trip type {trip.trip_type_master.trip_type.value}: {e}"
                    )
                    cancellation_policy = None

            elif trip.trip_type_master.trip_type in [TripTypeEnum.outstation]:
                state_code = trip.origin.state_code
                try:
                    cancellation_policy = config_store.outstation.get(
                        state_code
                    ).auxiliary_pricing.cancellation_policy.get(
                        trip.trip_type_master.id
                    )
                except Exception as e:
                    log.error(
                        f"Error while fetching cancellation policy for trip {trip.id} with state code {state_code} and trip type {trip.trip_type_master.trip_type.value}: {e}"
                    )
                    cancellation_policy = None

            else:
                log.info(
                    f"No automatic refund policy for trip type {trip.trip_type_master.trip_type.value}; finance review required"
                )
                return await _record_refund_review(
                    trip, db, refund_errors.UNSUPPORTED_REFUND_POLICY, requestor, commit)
            # Missing policy is unknown entitlement: retain a review record.

            if not cancellation_policy:

                log.info(
                    f"Cannot process refund workflow. Reason: No cancelation policy defined for '{trip.trip_type_master.trip_type.value}' trips in this state/region. To issue a refund for this trip, please create a cancellation policy for trip type '{trip.trip_type_master.trip_type.value}' in the config store with appropriate data based on your business rules."
                )
                return await _record_refund_review(
                    trip, db, refund_errors.MISSING_CANCELLATION_POLICY, requestor, commit)
            # Check if the cancellation is eligible for refund based on the cancellation policy and the time of cancellation
            free_cutoff_minutes = cancellation_policy.free_cutoff_minutes
            cancelation_time = (
                trip.cancellation.created_at
                if trip.cancellation and trip.cancellation.created_at
                else datetime.now(timezone.utc)
            )
            if trip.start_datetime is None:
                return await _record_refund_review(
                    trip, db, refund_errors.MISSING_TRIP_START_TIME, requestor, commit)
            # MySQL DateTime may arrive without tzinfo; policy calculations use UTC.
            cancelation_time = cancelation_time.replace(tzinfo=cancelation_time.tzinfo or timezone.utc)
            start_datetime = trip.start_datetime.replace(tzinfo=trip.start_datetime.tzinfo or timezone.utc)
            # If cancellation is done before free cutoff time, then full refund is applicable, if cancellation is done after free cutoff time but before trip start time, then partial refund is applicable, if cancellation is done after trip start time, then no refund is applicable.
            # trip.start_datetime and cancelation_time < trip.start_datetime
            if cancelation_time < start_datetime:
                time_diff = (
                    start_datetime - cancelation_time
                ).total_seconds() / 60  # Time difference in minutes
                if (
                    time_diff >= free_cutoff_minutes
                ):  # Cancellation is done before or at free cutoff time, then full refund is applicable
                    log.info(
                        f"Cancellation for trip {trip.id} is done before free cutoff time, hence eligible for full refund"
                    )
                    eligible_for_full_refund = True
                    refund_amount = trip.advance_payment
                else:  # Cancellation is done after free cutoff time but before trip start time, then partial refund is applicable
                    log.info(
                        f"Cancellation for trip {trip.id} is done after free cutoff time but before trip start time, hence eligible for partial refund based on cancellation policy with refund percentage {cancellation_policy.refund_percentage}%"
                    )
                    eligible_for_partial_configuration_based_refund = True
                    refund_amount = (
                        cancellation_policy.refund_percentage
                        * trip.advance_payment
                        / 100
                    )
            else:  # Cancellation is done after trip start time, then no refund is applicable
                if cancelation_time >= start_datetime:
                    log.info(
                        f"Cancellation for trip {trip.id} is done after trip start time, hence not eligible for refund"
                    )

                    eligible_for_full_refund = False
                    eligible_for_partial_configuration_based_refund = False
                    refund_amount = 0.0

        if (
            refund_amount > 0.0
            and (
                eligible_for_full_refund
                or eligible_for_partial_configuration_based_refund
            )
        ):
            log.info(
                f"Refund amount calculated for trip {trip.id} is {refund_amount} with eligible_for_full_refund={eligible_for_full_refund} and eligible_for_partial_configuration_based_refund={eligible_for_partial_configuration_based_refund}"
            )
            currency_symbol = config_store.geographies.country_server.currency_symbol
            log.info(
                    f"Queueing refund intent for {currency_symbol}{refund_amount} for trip {trip.id} through payment provider {settings.PAYMENT_PROVIDER}"
            )
            key = f"{settings.PAYMENT_PROVIDER}_payment_id"
            payment_id = (trip.payment_provider_metadata or {}).get(key)
            if not payment_id:
                log.error(
                    f"No payment ID found in payment_provider_metadata for trip {trip.id}, cannot initiate refund"
                )
                # Preserve the obligation; the worker can recover the ID or flag review.

            if not trip.customer:
                log.error(
                    f"No customer information found for trip {trip.id}, cannot initiate refund"
                )
            refund_type = (
                RefundType.full if eligible_for_full_refund else RefundType.partial
            )

            policy_id = get_cancelation_policy_id(policy=cancellation_policy)
            refund_status = RefundStatus.initiated

            refund_description = f"Queued {refund_type.value} refund for cancellation of trip {trip.id} with cancellation sub status {cancelation_sub_status.value}"
            notes = PaymentNotesSchema(
                reference_source_id=trip.id,
                refund_type=refund_type.value,
                canceled_by_cabbo=canceled_by_cabbo,
                original_amount=trip.advance_payment,
                refund_amount=refund_amount,
                requestor=trip.customer.id if trip.customer else requestor,
                customer=CustomerPayment(
                    id=trip.customer.id if trip.customer else None,
                    name=trip.customer.name if trip.customer else "",
                ),
            )

            currency = Currency(
                code=config_store.geographies.country_server.currency,
                lowest_unit_conversion_factor=config_store.geographies.country_server.currency_lowest_unit_conversion_factor,
            )

            initial_refund_response = get_initial_refund_response(
                payment_id=payment_id,
                refund_amount=refund_amount,
                notes=notes,
                currency=currency,
            )
            initial_refund_response.update(
                _currency_code=currency.code,
                _currency_factor=currency.lowest_unit_conversion_factor,
            )

            new_refund_record = await _add_refund_details_for_trip(
                refund=RefundSchema(
                    id=str(uuid4()),
                    policy_id=policy_id,
                    entity_id=trip.id,
                    refund_status=refund_status,
                    refund_amount=refund_amount,
                    refund_description=refund_description,
                    refund_details=initial_refund_response,
                    refund_initiated_datetime=datetime.now(timezone.utc),
                    refund_type=refund_type,
                    refund_provider=PaymentProvider(settings.PAYMENT_PROVIDER),
                ),
                db=db,
                created_by=requestor or RoleEnum.system.value,
                commit=False,  # Cancellation and refund intent share the caller's transaction.
            )
            if not new_refund_record:
                log.error(
                    f"Failed to add refund details in the database for trip {trip.id} after refund initiation, rolling back the transaction"
                )
                raise RuntimeError("Could not persist cancellation refund intent")
            log.info(
                f"Refund details added in the database for trip {trip.id} after refund initiation with refund amount {refund_amount} and refund description: {refund_description}"
            )

            if commit:
                await db.commit()
            # Provider submission and both emails belong to the durable worker.
            return True
        else:
            log.info(
                f"No refund applicable for trip {trip.id} based on the cancellation policy and timing"
            )
        return False
    except Exception as e:
        import traceback

        traceback.print_exc()
        await db.rollback()
        log.error(f"Error in refund_advance_payment_to_customer: {e}")
        # Log the exception or handle it as needed
        if not silently_fail or not commit:
            raise e
        return False


async def _record_refund_review(trip, db, reason, requestor, commit):
    """Missing policy is uncertainty, not proof that a paid cancellation owes zero."""
    saved = await _add_refund_details_for_trip(
        refund=RefundSchema(id=str(uuid4()), entity_id=trip.id,
            refund_amount=0.0, refund_status=RefundStatus.unknown,
            refund_description="Refund eligibility and amount require finance review",
            refund_provider=PaymentProvider(settings.PAYMENT_PROVIDER),
            refund_type=RefundType.other, review_required=True, last_error=reason,
            refund_details={"eligibility_unresolved": True, "payment_amount": trip.advance_payment},
            refund_initiated_datetime=datetime.now(timezone.utc)),
        created_by=requestor, db=db, commit=False)
    if not saved:
        raise RuntimeError("Could not persist refund eligibility review")
    if commit:
        await db.commit()
    return True


async def _update_refund_details_for_trip(
    refund: RefundSchema,
    db: AsyncSession,
    commit: bool = True,
) -> bool:

    try:
        result = await db.execute(
            select(RefundORM).where(
                (
                    (RefundORM.entity_id == refund.entity_id)
                    | (RefundORM.id == refund.id)
                )
                & (RefundORM.is_active == True)
            )
        )
        refund_record = result.scalars().first()
        if refund_record:
            refund_record.policy_id = refund.policy_id
            refund_record.refund_status = refund.refund_status
            refund_record.refund_amount = refund.refund_amount
            refund_record.refund_description = refund.refund_description
            refund_record.refund_details = refund.refund_details
            refund_record.refund_type = refund.refund_type
            refund_record.refund_provider = refund.refund_provider
            refund_record.refund_retried_datetime = refund.refund_retried_datetime
            await db.flush()
            if commit:
                await db.commit()
                log.info(
                    f"Refund details updated for entity {refund.entity_id} with refund amount {refund.refund_amount} and refund description {refund.refund_description}"
                )
            return True
        return False
    except Exception as e:
        await db.rollback()
        log.error(f"Error in _update_refund_details_for_trip: {e}")
        return False


async def _add_refund_details_for_trip(
    refund: RefundSchema,
    created_by: str,
    db: AsyncSession,
    commit: bool = True,
):

    try:
        # Add refund details to the refund table and link it to the trip using the entity_id field in the refunds table which is populated with the trip id when a refund is initiated for the trip and the refund record is created in the refunds table.
        refund_record = RefundORM(
            id=refund.id,
            entity_id=refund.entity_id,
            policy_id=refund.policy_id,
            refund_status=refund.refund_status,
            refund_amount=refund.refund_amount,
            refund_description=refund.refund_description,
            refund_details=refund.refund_details,
            refund_initiated_datetime=refund.refund_initiated_datetime,
            refund_type=refund.refund_type,
            refund_provider=refund.refund_provider,
            created_by=created_by,
            payment_id=(refund.refund_details or {}).get("payment_id"),
            idempotency_key=str(uuid5(NAMESPACE_URL, f"cabbo:refund:{refund.entity_id}")),
            review_required=refund.review_required,
            last_error=refund.last_error,
        )
        db.add(refund_record)
        await db.flush()
        if commit:
            await db.commit()
            log.info(
                f"Refund details updated for entity {refund.entity_id} with refund amount {refund.refund_amount} and refund description {refund.refund_description}"
            )
        return True
    except Exception as e:
        await db.rollback()
        log.error(f"Error in _add_refund_details_for_trip: {e}")
        return False


async def get_refund_details_by_trip_id(
    trip_id: str, db: AsyncSession
) -> Optional[RefundSchema]:
    try:
        result = await db.execute(
            select(RefundORM).where(
                RefundORM.entity_id == trip_id, RefundORM.is_active == True
            )
        )
        # This will return None if no record is found, or the record if found. It will raise an exception if multiple records are found, but that should not happen as we should have only one refund record for a trip based on our current design where we create/update refund record for a trip based on the trip id in the entity_id field of the refunds table.
        refund_record = result.scalar_one_or_none()
        if refund_record:
            return RefundSchema.model_validate(refund_record)
        return None
    except Exception as e:
        import traceback

        traceback.print_exc()
        log.error(f"Error in get_refund_details_by_trip_id: {e}")
        # Log the exception or handle it as needed
        return None


async def remove_refund_details_by_trip_id(
    trip_id: str, db: AsyncSession, hard_delete=False
) -> bool:
    try:
        result = await db.execute(
            select(RefundORM).where(
                RefundORM.entity_id == trip_id, RefundORM.is_active == True
            )
        )

        refund_record = result.scalar_one_or_none()
        if refund_record:
            if hard_delete:
                await db.delete(refund_record)
            else:
                refund_record.is_active = False  # Soft delete the refund record
            await db.commit()
            log.info(f"Refund details removed for trip {trip_id}")
            return True
        log.info(f"No active refund record found for trip {trip_id} to remove")
        return False
    except Exception as e:
        await db.rollback()
        log.error(f"Error in remove_refund_details_by_trip_id: {e}")
        # Log the exception or handle it as needed
        return False


async def _update_refund_status(
    refund_id: str, new_status: RefundStatus, db: AsyncSession
) -> bool:

    try:
        result = await db.execute(
            select(RefundORM).where(
                RefundORM.id == refund_id, RefundORM.is_active == True
            )
        )

        refund_record = result.scalar_one_or_none()
        if refund_record:
            refund_record.refund_status = new_status
            db.add(refund_record)
            await db.commit()
            log.info(
                f"Refund status updated to {new_status.value} for refund ID {refund_id}"
            )
            return True
        log.info(f"No active refund record found for refund ID {refund_id} to update")
        return False
    except Exception as e:
        await db.rollback()
        log.error(f"Error in _update_refund_status: {e}")
        # Log the exception or handle it as needed
        return False


async def _is_existing_refund(id: str, db: AsyncSession, silently_fail: bool = False):

    # Check DB for existing refund record
    existing_refund = await get_refund_details_by_trip_id(trip_id=id, db=db)
    if existing_refund:
        log.info(
            f"Refund record already exists for trip {id} with status {existing_refund.refund_status.value}, skipping. Scheduler will handle it as applicable."
        )
        return True
    return False


async def fetch_refund_detail_by_booking_id_and_customer_id(
    booking_id: str, requestor: str, db: AsyncSession
) -> Optional[RefundSchema]:
    try:
        result = await db.execute(
            select(RefundORM)
            .join(Trip, RefundORM.entity_id == Trip.id)
            .where(
                Trip.booking_id == booking_id,
                RefundORM.is_active == True,
                Trip.creator_id == requestor,
                Trip.creator_type == RoleEnum.customer,
                Trip.is_active == True,
            )
        )
        refund_record = result.scalar_one_or_none()
        if refund_record:
            return RefundSchema.model_validate(
                {
                    c.key: getattr(refund_record, c.key)
                    for c in RefundORM.__table__.columns
                    if c.key in RefundSchema.model_fields.keys()
                }
            )
        return None
    except Exception as e:
        import traceback

        traceback.print_exc()
        log.error(f"Error in fetch_refund_detail_by_booking_id_and_customer_id: {e}")
        return None

 

async def fetch_refund_details_by_customer_id(
    customer_id: str, db: AsyncSession
) -> list[RefundSchema]:
    try:
        result = await db.execute(
            select(RefundORM)
            .join(Trip, RefundORM.entity_id == Trip.id)
            .where(
                Trip.creator_id == customer_id,
                Trip.creator_type == RoleEnum.customer,
                Trip.is_active == True,
                RefundORM.is_active == True,
            )
        )
        refund_records = result.scalars().all()
        return [
            RefundSchema.model_validate(
                {
                    c.key: getattr(refund_record, c.key)
                    for c in RefundORM.__table__.columns
                    if c.key in RefundSchema.model_fields.keys()
                }
            )
            for refund_record in refund_records
        ]
    except Exception as e:
        import traceback

        traceback.print_exc()
        log.error(f"Error in fetch_refund_details_by_customer_id: {e}")
        return []


async def fetch_all_refund_details(db: AsyncSession) -> list[RefundSchema]:
    try:
        result = await db.execute(select(RefundORM).where(RefundORM.is_active == True))
        refund_records = result.scalars().all()
        return [
            RefundSchema.model_validate(
                {
                    c.key: getattr(refund_record, c.key)
                    for c in RefundORM.__table__.columns
                    if c.key in RefundSchema.model_fields.keys()
                }
            )
            for refund_record in refund_records
        ]
    except Exception as e:
        import traceback

        traceback.print_exc()
        log.error(f"Error in fetch_all_refund_details: {e}")
        return []


async def fetch_refund_detail_by_refund_id(
    refund_id: str, db: AsyncSession
) -> Optional[RefundSchema]:
    try:
        result = await db.execute(
            select(RefundORM).where(
                (RefundORM.id == refund_id) | (RefundORM.provider_refund_id == refund_id),
                RefundORM.is_active == True,
            )
        )
        refund_record = result.scalar_one_or_none()
        if refund_record:
            return RefundSchema.model_validate(
                {
                    c.key: getattr(refund_record, c.key)
                    for c in RefundORM.__table__.columns
                    if c.key in RefundSchema.model_fields.keys()
                }
            )
        return None
    except Exception as e:
        import traceback

        traceback.print_exc()
        log.error(f"Error in fetch_refund_detail_by_refund_id: {e}")
        return None


async def fetch_refund_detail_by_booking_id(
    booking_id: str, db: AsyncSession, use_orm = False
) -> Optional[Union[RefundSchema, RefundORM]]:
    try:
        result = await db.execute(
            select(RefundORM)
            .join(Trip, RefundORM.entity_id == Trip.id)
            .where(
                Trip.booking_id == booking_id,
                RefundORM.is_active == True,
                Trip.is_active == True,
            )
        )
        refund_record = (
            result.scalar_one_or_none()
        )  # One trip can have only one refund record based on our current design where we create/update refund record for a trip based on the trip id in the entity_id field of the refunds table, so we are using scalar_one_or_none which will return None if no record is found, or the record if found. It will raise an exception if multiple records are found, but that should not happen as we should have only one refund record for a trip based on our current design where we create/update refund record for a trip based on the trip id in the entity_id field of the refunds table.
        if refund_record:
            if use_orm:
                return refund_record
            return RefundSchema.model_validate(
                {
                    c.key: getattr(refund_record, c.key)
                    for c in RefundORM.__table__.columns
                    if c.key in RefundSchema.model_fields.keys()
                }
            )
        return None
    except Exception as e:
        import traceback

        traceback.print_exc()
        log.error(f"Error in fetch_refund_detail_by_booking_id: {e}")
        return None


async def initiate_refund_by_booking_id(
    booking_id: str,
    requestor: str,
    db: AsyncSession,
    cancelation_sub_status: (
        CancellationSubStatusEnum | None
    ) = None,
    silently_fail: bool = False,
) -> bool:
    try:
        result = await db.execute(
            select(Trip).where(
                Trip.booking_id == booking_id,
                Trip.is_active == True,
            )
        )
        trip = result.scalar_one_or_none()
        if not trip:
            if not silently_fail:
                raise CabboException(
                    f"No active trip found for booking ID {booking_id}, cannot initiate refund",
                    status_code=404,
                    error_code=TRIP_NOT_FOUND,
                )
            log.info(
                f"No active trip found for booking ID {booking_id}, cannot initiate refund"
            )
            return False

        if trip.status != TripStatusEnum.cancelled:
            if not silently_fail:
                raise CabboException(
                    f"Trip with booking ID {booking_id} is not cancelled, current status is {trip.status.value}, cannot initiate refund for a trip which is not cancelled",
                    status_code=400,
                    error_code=GENERIC_EXCEPTION,
                )
            log.info(
                f"Trip with booking ID {booking_id} is  not cancelled, current status is {trip.status.value}, cannot initiate refund for a trip which is not cancelled"
            )
            return False

        await attach_relationships_to_trip(
            trip, db, view=TripResponseView.ADMIN_DETAIL
        )

        trip_schema = TripDetailSchema.model_validate(trip)
        # Recovery must use the original cancellation reason, not assume a
        # Cabbo cancellation and accidentally grant a full refund to a customer.
        if cancelation_sub_status is None:
            cancellation = trip_schema.cancellation
            cancelation_sub_status = cancellation.cancellation_sub_status if cancellation else None
        if cancelation_sub_status is None:
            return await _record_refund_review(
                trip_schema, db, refund_errors.MISSING_CANCELLATION_REASON, requestor, True)
        refund_initiated = await refund_advance_payment_to_customer_on_cancellation(
            trip=trip_schema,
            requestor=requestor,
            db=db,
            cancelation_sub_status=cancelation_sub_status,
            silently_fail=silently_fail,
        )
        return refund_initiated

    except Exception as e:
        import traceback

        traceback.print_exc()
        log.error(f"Error in initiate_refund_by_booking_id: {e}")
        # Log the exception or handle it as needed
        if not silently_fail:
            raise e
        return False


async def queue_refund_retry(refund_id: str, db: AsyncSession, requestor: str):
    """An explicit finance/admin request requeues validation, never bypasses it."""
    result = await db.execute(select(RefundORM).where(
        RefundORM.id == refund_id, RefundORM.is_active.is_(True)).with_for_update())
    refund = result.scalars().first()
    if refund is None:
        raise CabboException("Refund not found", status_code=404, error_code=TRIP_NOT_FOUND)
    if (refund.refund_details or {}).get("eligibility_unresolved"):
        raise CabboException("Refund eligibility requires finance review before retrying",
                             status_code=409, error_code=GENERIC_EXCEPTION)
    # Keep payment/provider identity and idempotency intact on manual retries.
    refund.review_required = False #Means, make it eligible to be picked up by the refund scheduler. Refer @process_refund.py under src/scheduler/tasks
    refund.next_attempt_at = datetime.now(timezone.utc)
    details = dict(refund.refund_details or {})
    # An explicit admin retry starts a fresh budget without losing the previous
    # count/error or changing the provider identity and idempotency key.
    details["retry_previous_attempts"] = refund.attempts or 0
    details["retry_previous_error"] = refund.last_error
    details["retry_requested_at"] = datetime.now(timezone.utc).isoformat()
    refund.attempts = 0
    details["retry_requested_by"] = requestor
    refund.refund_details = details
    await db.commit()


async def send_refund_credited_notification(
    refund: RefundORM, trip: Trip, provider_refund_id: str
):
    """
    Notify provider-processed status, not independently verified bank credit.
    Return actual email acceptance so the worker can retry failed delivery.

    """
    try:
        from core.config import settings

        config_store = settings.get_config_store()
        decimal_places = (
                config_store.geographies.country_server.currency_decimal_places
            )
        currency = config_store.geographies.country_server.currency_symbol

        formatted_refund_amount = f"{refund.refund_amount:.{decimal_places}f}"
        formatted_original_amount = f"{trip.advance_payment:.{decimal_places}f}"
        customer = CustomerRead.model_validate(trip.customer)
        sent = await notify_refund_processed_to_customer(
            customer=customer,
            refund_id=provider_refund_id,
            refund_amount=formatted_refund_amount,
            booking_id=trip.booking_id,
            currency=currency,
            original_amount=formatted_original_amount,
            refund_type=refund.refund_type.value if refund.refund_type else "full",
        )

        
        if not sent:
            return False
        log.info(
            f"[process_refund] Sent refund processed notification for refund {refund.id} "
            f"(entity={refund.entity_id}) to customer {customer.id}"
        )
        return True

    except Exception as e:
        
        log.error(
            f"[process_refund] Failed to send refund-credited notification "
            f"for refund {refund.id}: {e}"
        )
        return False


async def inactivate_refund(refund: RefundORM, db: AsyncSession):
    refund.is_active = False
    db.add(refund)
    await db.commit()
    await db.refresh(refund)
    log.info(f"Refund {refund.id} has been inactivated")


def serialize_refund(refund, trip_dict: dict):
    refund = RefundSchema.model_validate(refund)
    refund_data = refund.model_dump()
    trip_dict["refund"] = refund_data
    trip_dict["refund"].pop("id", None)
    trip_dict["refund"].pop("entity_id", None)
    return trip_dict
