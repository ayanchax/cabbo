from datetime import datetime, timezone
from typing import Optional
from core.security import RoleEnum
from core.store import ConfigStore
from db.database import get_mysql_local_session
from models.customer.customer_schema import CustomerPayment
from models.financial.payments_schema import PaymentNotesSchema
from models.policies.cancelation_schema import CancelationPolicySchema
from models.policies.refund_enum import PaymentProvider, RefundStatus, RefundType
from models.pricing.pricing_schema import Currency
from models.trip.trip_enums import CancellationSubStatusEnum, TripTypeEnum
from models.trip.trip_schema import TripDetailSchema
from models.policies.refund_orm import Refund as RefundORM
from models.policies.refund_schema import RefundSchema
from core.config import settings
from sqlalchemy import select

from services.cancelation_service import get_cancelation_policy_id
from sqlalchemy.ext.asyncio import AsyncSession

from services.notification_service import notify_refund_initiated_to_customer
from services.payment_service import get_refund_status, initiate_refund


async def refund_advance_payment_to_customer_on_cancellation(
    trip: TripDetailSchema,
    db: AsyncSession,
    cancelation_sub_status: CancellationSubStatusEnum,
    config_store: ConfigStore = None,
    silently_fail: bool = False,
    requestor: str = None,
):
    try:
        can_proceed = await _can_proceed_to_refund_initiation(id=trip.id, db=db, silently_fail=silently_fail)
        if not can_proceed:
            print(
                f"Refund initiation for trip {trip.id} is already in process or completed, hence skipping refund initiation"
            )
            return False
        # Determine if the cancellation is done by cabbo or by driver or due to any other reason except customer cancellation or customer no show, because if the customer is canceling the trip then they should be responsible for any cancellation charges and we should not refund the advance payment in that case or refund partially. But if the trip is canceled by cabbo or by driver admin or due to any other reason except customer cancellation, then we should refund the advance payment to customer in full because it is not the fault of customer and they should not be penalized for that.
        canceled_by_cabbo = cancelation_sub_status not in [
            CancellationSubStatusEnum.customer_cancelled,
            CancellationSubStatusEnum.customer_no_show,
        ]

        if not config_store:
            syncdb = get_mysql_local_session()
            config_store = settings.get_config_store(db=syncdb)

        if trip.advance_payment is None or trip.advance_payment <= 0.0:
            print(f"No advance payment to refund for trip {trip.id}")
            return False

         
        eligible_for_partial_configuration_based_refund = False
        eligible_for_full_refund = False
        refund_amount = 0.0
        cancellation_policy :Optional[CancelationPolicySchema] = None
        if canceled_by_cabbo:
            eligible_for_full_refund = True
            refund_amount = trip.advance_payment
        else:
            # For customer no show cases(reported by driver to driver admin), we will not refund the advance payment as it is the responsibility of customer to cancel the trip in time if they are not going to use it and if they do a no show then it is not the fault of cabbo and hence we should not refund the advance payment in that case.
            if cancelation_sub_status == CancellationSubStatusEnum.customer_no_show:
                print(
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
                        cancellation_policy = config_store.airport_drop.get(region_code).auxiliary_pricing.cancellation_policy
                    elif trip.trip_type_master.trip_type == TripTypeEnum.airport_pickup:
                        cancellation_policy = config_store.airport_pickup.get(region_code).auxiliary_pricing.cancellation_policy
                    elif trip.trip_type_master.trip_type == TripTypeEnum.local:
                        cancellation_policy = config_store.local.get(region_code).auxiliary_pricing.cancellation_policy
                except Exception as e:
                    print(
                        f"Error while fetching cancellation policy for trip {trip.id} with region code {region_code} and trip type {trip.trip_type_master.trip_type.value}: {e}"
                    )
                    cancellation_policy = None

            elif trip.trip_type_master.trip_type in [TripTypeEnum.outstation]:
                state_code = trip.origin.state_code
                try:
                    cancellation_policy = config_store.outstation.get(state_code).auxiliary_pricing.cancellation_policy
                except Exception as e:
                    print(
                        f"Error while fetching cancellation policy for trip {trip.id} with state code {state_code} and trip type {trip.trip_type_master.trip_type.value}: {e}"
                    )
                    cancellation_policy = None

            else:
                print(
                    f"Trip type {trip.trip_type_master.trip_type.value} not eligible for cancellation refund"
                )
                return False
            
            
            if not cancellation_policy:

                print(
                    f"Cannot process refund workflow. Reason: No cancelation policy defined for'{trip.trip_type_master.trip_type.value}' trips in this state/region. To issue a refund for this trip, please create a cancellation policy for trip type '{trip.trip_type_master.trip_type.value}' in the config store with appropriate data based on your business rules."
                )
                return False
            # Check if the cancellation is eligible for refund based on the cancellation policy and the time of cancellation
            free_cutoff_minutes = cancellation_policy.free_cutoff_minutes
            cancelation_time = (
                trip.cancellation.created_at
                if trip.cancellation and trip.cancellation.created_at
                else datetime.now(timezone.utc)
            )
            # If cancellation is done before free cutoff time, then full refund is applicable, if cancellation is done after free cutoff time but before trip start time, then partial refund is applicable, if cancellation is done after trip start time, then no refund is applicable.
            if trip.start_datetime and cancelation_time < trip.start_datetime:
                time_diff = (
                    trip.start_datetime - cancelation_time
                ).total_seconds() / 60  # Time difference in minutes
                if (
                    time_diff >= free_cutoff_minutes
                ):  # Cancellation is done before or at free cutoff time, then full refund is applicable
                    eligible_for_full_refund = True
                    refund_amount = trip.advance_payment
                else:  # Cancellation is done after free cutoff time but before trip start time, then partial refund is applicable
                    eligible_for_partial_configuration_based_refund = True
                    refund_amount = (
                        cancellation_policy.refund_percentage
                        * trip.advance_payment
                        / 100
                    )
            else:  # Cancellation is done after trip start time, then no refund is applicable
                if cancelation_time > trip.start_datetime:
                    print(
                        f"Cancellation for trip {trip.id} is done after trip start time, hence not eligible for refund"
                    )

                    eligible_for_full_refund = False
                    eligible_for_partial_configuration_based_refund = False
                    refund_amount = 0.0

        print(
            f"Refund amount calculated for trip {trip.id} is {refund_amount} with eligible_for_full_refund={eligible_for_full_refund} and eligible_for_partial_configuration_based_refund={eligible_for_partial_configuration_based_refund}"
        )
        if (
            refund_amount > 0.0
            and trip.payment_provider_metadata
            and (
                eligible_for_full_refund
                or eligible_for_partial_configuration_based_refund
            )
        ):
            currency_symbol = config_store.geographies.country_server.currency_symbol
            print(
                f"Initiating refund of amount {currency_symbol}{refund_amount} for trip {trip.id} through payment provider"
            )
            key = f"{settings.PAYMENT_PROVIDER}_payment_id"
            payment_id = trip.payment_provider_metadata.get(key)
            if not payment_id:
                print(
                    f"No payment ID found in payment_provider_metadata for trip {trip.id}, cannot initiate refund"
                )
                return False

            if not trip.customer:
                print(
                    f"No customer information found for trip {trip.id}, cannot initiate refund"
                )
                return False
            refund_type = (
                RefundType.full if eligible_for_full_refund else RefundType.partial
            )
            notes = PaymentNotesSchema(
                reference_source_id=trip.id,
                refund_type=refund_type.value,
                canceled_by_cabbo=canceled_by_cabbo,
                original_amount=trip.advance_payment,
                refund_amount=refund_amount,
                requestor=trip.customer.id,
                customer=CustomerPayment(
                    id=trip.customer.id,
                    name=trip.customer.name,
                    email=trip.customer.email or None,
                    contact=trip.customer.phone_number,
                ),
            )
            key = f"{settings.PAYMENT_PROVIDER}_payment_id"
            refund_response = initiate_refund(
                payment_id=trip.payment_provider_metadata.get(key),
                refund_amount=refund_amount,
                notes=notes,
                currency=Currency(
                    code=config_store.geographies.country_server.currency,
                    lowest_unit_conversion_factor=config_store.geographies.country_server.currency_lowest_unit_conversion_factor,
                ),
                silently_fail=silently_fail,
            )
            if silently_fail and not refund_response:
                #This will happen only when the refund initiation fails at payment provider level and silently_fail flag is set to True, in that case we will not update the refund details in the database and we will not send notification to customer about the refund initiation failure because it is expected as per the flag and we are silently failing it, so just log it and move on without doing anything as refund initiation failure is expected in this case due to silently_fail flag being True.
                print(
                    f"Refund initiation failed for trip {trip.id} but silently failing as per the flag, hence skipping refund details update and notification sending to customer"
                )
                return False

            
            # Add refund details to the refunds table and link it to the trip using the entity_id field in the refunds table which is populated with the trip id when a refund is initiated for the trip and the refund record is created in the refunds table.
            policy_id = get_cancelation_policy_id(policy=cancellation_policy)
            refund_reason = (
                f"Refund for {refund_type.value} cancellation of trip {trip.id} with cancellation sub status {cancelation_sub_status.value}"
            )
            updated = await _add_refund_details_for_trip(
                refund=RefundSchema(
                    id=refund_response.get("id"),
                    policy_id=policy_id,
                    entity_id=trip.id,
                    refund_status=refund_response.get("status"),
                    refund_amount=refund_amount,
                    refund_reason=refund_reason,
                    refund_details=refund_response,
                    refund_initiated_datetime=datetime.now(timezone.utc),
                    refund_type=refund_type,
                    refund_provider=PaymentProvider(settings.PAYMENT_PROVIDER),
                ),
                db=db,
                created_by=requestor or RoleEnum.system.value,
                commit=False,  # We will commit after sending notification to customer, so that if there is any failure in sending notification to customer then we can rollback the transaction and not save the refund details in the database because it is important to send notification to customer about the refund initiation and if we fail to send notification to customer then it can lead to bad customer experience and confusion for customer about the refund status. So we will commit the transaction only after successfully sending notification to customer.
            )
            if updated:
                print(f"Refund details updated successfully for trip {trip.id}")
                decimal_places = (
                    config_store.geographies.country_server.currency_decimal_places
                )
                formatted_refund_amount = f"{refund_amount:.{decimal_places}f}"
                formatted_original_amount = f"{trip.advance_payment:.{decimal_places}f}"
                # Send notification to customer about the refund. This is a placeholder and should be replaced with actual implementation to send notification to the customer.
                await notify_refund_initiated_to_customer(
                    customer=trip.customer,
                    refund_id=refund_response.get("id"),
                    refund_amount=formatted_refund_amount,
                    refund_type=refund_type,
                    currency=config_store.geographies.country_server.currency_symbol,
                    booking_id=trip.booking_id,
                    original_amount=formatted_original_amount,
                )
                await db.commit()
            else:
                print(
                    f"Refund initiated but Failed to update refund details for trip {trip.id}"
                )

            return True
        else:
            print(
                f"No refund applicable for trip {trip.id} based on the cancellation policy and timing"
            )
        return False
    except Exception as e:
        import traceback

        traceback.print_exc()
        await db.rollback()
        print(f"Error in refund_advance_payment_to_customer: {e}")
        # Log the exception or handle it as needed
        if not silently_fail:
            raise e
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
            refund_reason=refund.refund_reason,
            refund_details=refund.refund_details,
            refund_initiated_datetime=refund.refund_initiated_datetime,
            refund_type=refund.refund_type,
            refund_provider=refund.refund_provider,
            created_by=created_by,
        )
        db.add(refund_record)
        await db.flush()
        if commit:
            await db.commit()
            print(
                f"Refund details updated for entity {refund.entity_id} with refund amount {refund.refund_amount} and refund reason {refund.refund_reason}"
            )
        return True
    except Exception as e:
        await db.rollback()
        print(f"Error in _add_refund_details_for_trip: {e}")
        # Log the exception or handle it as needed
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
        refund_record = result.scalars().first()
        if refund_record:
            return RefundSchema.model_validate(refund_record)
        return None
    except Exception as e:
        print(f"Error in get_refund_details_by_trip_id: {e}")
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

        refund_record = result.scalars().first()
        if refund_record:
            if hard_delete:
                await db.delete(refund_record)
            else:
                refund_record.is_active = False  # Soft delete the refund record
            await db.commit()
            print(f"Refund details removed for trip {trip_id}")
            return True
        print(f"No active refund record found for trip {trip_id} to remove")
        return False
    except Exception as e:
        await db.rollback()
        print(f"Error in remove_refund_details_by_trip_id: {e}")
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

        refund_record = result.scalars().first()
        if refund_record:
            refund_record.refund_status = new_status
            db.add(refund_record)
            await db.commit()
            print(
                f"Refund status updated to {new_status.value} for refund ID {refund_id}"
            )
            return True
        print(f"No active refund record found for refund ID {refund_id} to update")
        return False
    except Exception as e:
        await db.rollback()
        print(f"Error in _update_refund_status: {e}")
        # Log the exception or handle it as needed
        return False


async def _can_proceed_to_refund_initiation(id: str, db: AsyncSession, silently_fail: bool = False) -> bool:

    #     1. Check DB for existing refund record
    #    └─ If exists with status=processed → return True (done, nothing to do)
    #    └─ If exists with status=pending   → check Razorpay for current status
    #        └─ processed → update DB, return True
    #        └─ still pending → return True (in-flight, don't retry)
    #        └─ failed → fall through to retry refund initiation
    #    └─ If exists with status=failed    → fall through to retry
    #    └─ If no DB record                 → fall through to fresh initiation
    # Check DB for existing refund record
    existing_refund = await get_refund_details_by_trip_id(trip_id=id, db=db)
    if existing_refund:
        if existing_refund.refund_status == RefundStatus.processed:
            print(f"Refund already processed for trip {id}, nothing to do")
            return False  # No need to proceed with refund initiation as refund is already processed for this trip
        elif existing_refund.refund_status == RefundStatus.pending:
            # Check Razorpay for current status
            razorpay_status = get_refund_status(existing_refund.id, silently_fail=silently_fail)
            if silently_fail and razorpay_status is None:
                # This will happen only when there is a failure at the payment provider level.
                print(
                    f"Failed to get refund status from payment provider for refund ID {existing_refund.id} but silently failing as per the flag, hence treating it as still pending and not retrying refund initiation to avoid duplicate refunds"
                )
                return False
            
            if razorpay_status == RefundStatus.processed:
                # Update DB and return, no need to retry refund initiation as it is already processed in Razorpay, just update our DB to reflect the correct status
                await _update_refund_status(
                    existing_refund.id, RefundStatus.processed, db
                )
                return False
            elif razorpay_status == RefundStatus.pending:
                # Still pending, return True (in-flight, don't retry as there are no changes pending->pending)
                return False
            elif razorpay_status == RefundStatus.failed:
                # Sync DB to reflect actual Razorpay state before retrying
                await _update_refund_status(existing_refund.id, RefundStatus.failed, db)
                # Fall through to retry refund initiation
                return True
        elif existing_refund.refund_status == RefundStatus.failed:
            # Fall through to retry refund initiation
            return True
    return True  # No existing refund record found, can proceed with refund initiation
