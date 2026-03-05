from datetime import datetime, timezone
from core.security import RoleEnum
from core.store import ConfigStore
from db.database import get_mysql_local_session
from models.customer.customer_schema import CustomerPayment
from models.financial.payments_schema import PaymentNotesSchema
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_schema import TripDetailSchema
from models.policies.refund_orm import Refund as RefundORM
from models.policies.refund_schema import RefundSchema
from core.config import settings

from services.geography_service import (
    async_get_region_by_code,
    async_get_state_by_state_code,
)
from sqlalchemy.ext.asyncio import AsyncSession

from services.notification_service import notify_refund_initiated_to_customer
from services.payment_service import initiate_razorpay_refund


async def refund_advance_payment_to_customer(
    trip: TripDetailSchema,
    db: AsyncSession,
    canceled_by_cabbo: bool = False,
    config_store: ConfigStore = None,
    silently_fail: bool = False,
    requestor: str = None,
):
    try:
        if not config_store:
            syncdb = get_mysql_local_session()
            config_store = ConfigStore(syncdb)

        if trip.advance_payment is None or trip.advance_payment <= 0.0:
            print(f"No advance payment to refund for trip {trip.id}")
            return False

        region_id = None
        state_id = None
        eligible_for_partial_configuration_based_refund = False
        eligible_for_full_refund = False
        refund_amount = 0.0
        if canceled_by_cabbo:
            eligible_for_full_refund = True
            refund_amount = trip.advance_payment
        else:

            if trip.trip_type.trip_type in [
                TripTypeEnum.airport_drop,
                TripTypeEnum.airport_pickup,
                TripTypeEnum.local,
            ]:
                region_code = trip.origin.region_code
                region = await async_get_region_by_code(region_code=region_code, db=db)
                if region:
                    region_id = region.id

            elif trip.trip_type.trip_type in [TripTypeEnum.outstation]:
                state_code = trip.origin.state_code
                state = await async_get_state_by_state_code(
                    state_code=state_code, db=db
                )
                if state:
                    state_id = state.id
            else:
                print(
                    f"Trip type {trip.trip_type.trip_type.value} not eligible for cancellation refund"
                )
                return False

            cancelation_configuration = {
                TripTypeEnum.airport_drop: config_store.airport_drop.get(
                    region_id
                ).auxiliary_pricing.cancellation_policy,
                TripTypeEnum.airport_pickup: config_store.airport_pickup.get(
                    region_id
                ).auxiliary_pricing.cancellation_policy,
                TripTypeEnum.local: config_store.local.get(
                    region_id
                ).auxiliary_pricing.cancellation_policy,
                TripTypeEnum.outstation: config_store.outstation.get(
                    state_id
                ).auxiliary_pricing.cancellation_policy,
            }
            cancelation_policy = cancelation_configuration.get(
                trip.trip_type.trip_type, None
            )

            if not cancelation_policy:
                print(
                    f"No cancelation policy found for trip type {trip.trip_type.trip_type.value}"
                )
                return False
            # Check if the cancellation is eligible for refund based on the cancellation policy and the time of cancellation
            free_cutoff_minutes = cancelation_policy.free_cutoff_minutes
            cancelation_time = (
                trip.cancelation_datetime
                if trip.cancelation_datetime
                else datetime.now(timezone.utc)
            )
            # If cancellation is done before free cutoff time, then full refund is applicable, if cancellation is done after free cutoff time but before trip start time, then partial refund is applicable, if cancellation is done after trip start time, then no refund is applicable.
            if trip.start_datetime and cancelation_time < trip.start_datetime:
                time_diff = (
                    trip.start_datetime - cancelation_time
                ).total_seconds() / 60  # Time difference in minutes
                if (
                    time_diff >= free_cutoff_minutes
                ):  # Cancellation is done before free cutoff time, then full refund is applicable
                    eligible_for_full_refund = True
                    refund_amount = trip.advance_payment
                else:  # Cancellation is done after free cutoff time but before trip start time, then partial refund is applicable
                    eligible_for_partial_configuration_based_refund = True
                    refund_amount = (
                        cancelation_policy.refund_percentage
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
            print(
                f"Initiating refund of amount {refund_amount} for trip {trip.id} through payment provider"
            )
            payment_id = trip.payment_provider_metadata.get("razorpay_payment_id")
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
            refund_type = "full" if eligible_for_full_refund else "partial"
            notes = PaymentNotesSchema(
                reference_source_id=trip.id,
                refund_type=refund_type,
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
            refund_response = initiate_razorpay_refund(
                payment_id=trip.payment_provider_metadata.get("razorpay_payment_id"),
                refund_amount=refund_amount,
                notes=notes,
                currency_conversion_factor=config_store.geographies.country_server.currency_lowest_unit_conversion_factor,
                silently_fail=silently_fail,
            )
            if not refund_response:
                print(
                    f"Refund initiation failed for trip {trip.id} through payment provider, refund_response is None"
                )
                return False

            if not refund_response.get("id"):
                print(
                    f"Refund initiation failed for trip {trip.id} through payment provider, refund_response does not contain refund ID"
                )
                return False

            # Update the trip record with refund details like refund amount, refund status, refund transaction id etc. This is a placeholder and should be replaced with actual implementation to update the trip record in the database.
            reason = (
                "Cancellation by Cabbo"
                if canceled_by_cabbo
                else "Cancellation by Customer"
            )
            updated = await update_refund_details_for_trip(
                trip_id=trip.id,
                refund=RefundSchema(
                    id=refund_response.get("id"),
                    entity_id=trip.id,
                    refund_status=refund_response.get("status"),
                    refund_amount=refund_amount,
                    refund_reason=reason,
                    refund_details=refund_response,
                    refund_initiated_datetime=datetime.now(timezone.utc),
                    refund_type=refund_type,
                    refund_provider=settings.PAYMENT_PROVIDER,
                ),
                db=db,
                created_by=requestor or RoleEnum.system.value,
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
            else:
                print(f"Failed to update refund details for trip {trip.id}")
                return False

            return True
        else:
            print(
                f"No refund applicable for trip {trip.id} based on the cancellation policy and timing"
            )
            return False
    except Exception as e:
        print(f"Error in refund_advance_payment_to_customer: {e}")
        # Log the exception or handle it as needed
        if not silently_fail:
            raise e
        return False


async def update_refund_details_for_trip(
    trip_id: str,
    refund: RefundSchema,
    created_by: str,
    db: AsyncSession,
):
    from services.trips.trip_service import async_get_trip_by_id

    try:
        trip = await async_get_trip_by_id(trip_id=trip_id, db=db)
        if not trip:
            print(f"Trip with id {trip_id} not found, cannot update refund details")
            return False

        trip.refund_id = refund.id

        # Add refund details to the refund table and link it to the trip using the entity_id field in the refunds table which is populated with the trip id when a refund is initiated for the trip and the refund record is created in the refunds table.
        refund_record = RefundORM(
            id=refund.id,
            entity_id=refund.entity_id,
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
        await db.commit()
        await db.refresh(trip)
        print(
            f"Refund details updated for trip {trip_id} with refund amount {refund.refund_amount} and refund reason {refund.refund_reason}"
        )
        return True
    except Exception as e:
        await db.rollback()
        print(f"Error in update_refund_details_for_trip: {e}")
        # Log the exception or handle it as needed
        return False
