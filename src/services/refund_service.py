from datetime import datetime, timezone
from core.store import ConfigStore
from db.database import get_mysql_local_session
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_schema import TripDetailSchema

from services.geography_service import (
    async_get_region_by_code,
    async_get_state_by_state_code,
)
from sqlalchemy.ext.asyncio import AsyncSession


async def refund_advance_payment_to_customer(
    trip: TripDetailSchema,
    db: AsyncSession,
    canceled_by_cabbo: bool = False,
    config_store: ConfigStore = None,
    silently_fail: bool = False,
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
            # Call the payment provider service to process the refund. This is a placeholder and should be replaced with actual implementation to call the payment provider's API.
            print(
                f"Initiating refund of amount {refund_amount} for trip {trip.id} through payment provider"
            )
            # Update the trip record with refund details like refund amount, refund status, refund transaction id etc. This is a placeholder and should be replaced with actual implementation to update the trip record in the database.
            # Send notification to customer about the refund. This is a placeholder and should be replaced with actual implementation to send notification to the customer.
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
