import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(parent_dir))
import asyncio
import logging
from sqlalchemy import select, and_
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import AsyncSessionLocal, get_mysql_local_session
from models.customer.customer_schema import CustomerRead
from models.policies.refund_orm import Refund as RefundORM
from models.policies.refund_enum import RefundStatus
from models.trip.trip_orm import Trip
from scheduler.task_registry import task
from services.payment_service import (
    get_refund_status,
    is_eligible_payment_identifier,
    is_eligible_to_attempt_refund_initiation,
)
from services.notification_service import notify_refund_processed_to_customer
from services.refund_service import inactivate_refund, attempt_refund_initiation

logger = logging.getLogger(__name__)

REFUND_POLL_BATCH_SIZE = 50


@task(
    task_id="sync_pending_refund_statuses",
    description="Polls payment provider for pending/failed/initiated refund statuses, updates DB, and notifies customer on credit",
)
def sync_pending_refund_statuses_task():
    asyncio.run(_run_refund_status_sync())


 
async def _run_refund_status_sync():
    async with AsyncSessionLocal() as db:
        try:
            refunds = await _fetch_actionable_refunds(db)
            if len(refunds) == 0:
                print("[process_refund] No pending/failed/initiated refunds to poll, exiting")
                logger.info(
                    "[process_refund] No pending/failed/initiated refunds to poll, exiting"
                )
                return
            print(
                f"[process_refund] Found {len(refunds)} pending/failed/initiated refunds to poll"
            )
            logger.info(
                f"[process_refund] Found {len(refunds)} pending/failed/initiated refunds to poll"
            )

            for refund in refunds:
                try:
                    await _process_single_refund(db, refund)
                except Exception as e:
                    print(
                        f"[process_refund] Error processing refund {refund.id} "
                        f"(entity={refund.entity_id}): {e}"
                    )
                    logger.error(
                        f"[process_refund] Error processing refund {refund.id} "
                        f"(entity={refund.entity_id}): {e}"
                    )
        except Exception as e:
            print(f"[process_refund] Unexpected error during refund status sync: {e}")
            logger.error(
                f"[process_refund] Unexpected error during refund status sync: {e}"
            )


async def _fetch_actionable_refunds(db: AsyncSession) -> list[RefundORM]:
    """
    Queries the refunds table for active pending/failed refunds whose linked trip
    exists and is not soft-deleted (Trip.is_active == True).
    """
    try:
        stmt = (
            select(RefundORM)
            .join(Trip, Trip.id == RefundORM.entity_id)
            .where(
                and_(
                    RefundORM.refund_status.in_(
                        [RefundStatus.pending, RefundStatus.failed, RefundStatus.initiated]
                    ),
                    RefundORM.is_active == True,
                    Trip.is_active == True,
                )
            )
            .options(joinedload(RefundORM.trip).joinedload(Trip.customer))
            .limit(REFUND_POLL_BATCH_SIZE)
        )
        result = await db.execute(stmt)
        return result.scalars().unique().all()
    except Exception as e:
        print(f"[process_refund] Error fetching actionable refunds from DB: {e}")
        logger.error(f"[process_refund] Error fetching actionable refunds from DB: {e}")
        return []


async def _process_single_refund(db: AsyncSession, refund: RefundORM):
    
    """
    For each refund, we first check if it has a valid provider refund ID in refund_details to determine if we can poll for status updates. 
    If it doesn't have a valid provider refund ID but has a payment ID (indicating a previous initiation or failed attempt),
    we can attempt refund initiation. If it has neither, 
    we inactivate the refund record to prevent future processing attempts until the data is fixed. 
    If it has a valid provider refund ID, we poll for status updates and if the status is "processed", we update the DB and 
    notify the customer that the refund is credited, so that the refund is not pickeded up again in the next sync cycle since 
    it's already processed and we avoid unnecessary polling and processing of already processed refunds, and also ensure timely notification to the customer once the refund is credited.

    """
    provider_refund_id = (refund.refund_details or {}).get("id")
    if not provider_refund_id:
        print(
            f"[process_refund] Refund {refund.id} has no provider refund ID in "
            f"refund_details, skipping"
        )
        logger.warning(
            f"[process_refund] Refund {refund.id} has no provider refund ID in "
            f"refund_details, skipping"
        )
        #Inactivate the refund record to prevent it from being picked up again in the next sync cycle since it doesn't have a valid provider refund ID to poll for status updates and it's likely a failed initiation attempt where refund_details contains payment details instead of refund details, so we can set is_active to False to exclude it from future sync attempts and avoid unnecessary polling and processing of invalid refund records.
        await inactivate_refund(refund, db)
        return
    
    #Neither refund ID nor payment ID in refund_details — can't do anything with this record, skip it and make it inactive for now and let support/finance investigate and fix the data if needed
    if not is_eligible_payment_identifier(str(provider_refund_id)):
        print(
            f"[process_refund] Refund {refund.id} has invalid provider refund or payment ID "
            f"{provider_refund_id!r} in refund_details, skipping"
        )
        logger.warning(
            f"[process_refund] Refund {refund.id} has invalid provider refund or payment ID "
            f"{provider_refund_id!r} in refund_details, skipping"
         )
        await inactivate_refund(refund, db)  # Inactivate the refund record since it has invalid provider refund ID and can't be processed in future sync cycles until the data is fixed, so we can set is_active to False to exclude it from future sync attempts and avoid unnecessary polling and processing of invalid refund records.
        return
     
    # At this point, we have a valid provider refund ID or payment ID in refund_details, so we can proceed with either polling for status updates (if it's a refund ID) or attempting refund initiation (if it's a payment ID indicating a previous initiation or failed attempt that may have failed before settlement).
    if is_eligible_to_attempt_refund_initiation(str(provider_refund_id)):
         await attempt_refund_initiation(payment_id=str(provider_refund_id), refund=refund, db=db)
         return
    
    # At this point, we have a valid provider refund ID in refund_details, so we can proceed with polling for status updates and processing accordingly.
    current_status = get_refund_status(
        refund_id=str(provider_refund_id), silently_fail=True
    )
    if current_status is None:
        print(
            f"[process_refund] Could not retrieve status from provider for refund ID "
            f"{provider_refund_id}, skipping"
        )
        logger.warning(
            f"[process_refund] Could not retrieve status from provider for refund ID "
            f"{provider_refund_id}, skipping"
        )
        return

    current_status_value = current_status.value if current_status else None

    if current_status_value is None:
        print(
            f"[process_refund] Provider returned unknown status {current_status} "
            f"for refund ID {provider_refund_id}, skipping"
        )
        logger.warning(
            f"[process_refund] Provider returned unknown status {current_status} "
            f"for refund ID {provider_refund_id}, skipping"
        )
        return

    existing_status_value = (
        str(refund.refund_status.value)
        if refund.refund_status and refund.refund_status.value
        else None
    )
    if current_status_value.lower() == existing_status_value.lower():
        print(
            f"[process_refund] Refund {refund.id} status unchanged ({current_status_value}), skipping, scheduler will check again in the next cycle"
        )

        logger.debug(
            f"[process_refund] Refund {refund.id} status unchanged ({current_status_value}), skipping, scheduler will check again in the next cycle"
        )
        return

    print(
        f"[process_refund] Refund {refund.id} (entity={refund.entity_id}) "
        f"status changed: {existing_status_value} → {current_status_value}"
    )
    logger.info(
        f"[process_refund] Refund {refund.id} (entity={refund.entity_id}) "
        f"status changed: {existing_status_value!r} → {current_status_value!r}"
    )

    try:
        new_db_status = RefundStatus(current_status_value)
    except ValueError:
        print(
            f"[process_refund] Unknown provider status {current_status_value!r} "
            f"for refund {refund.id}, skipping DB update, scheduler will check again in the next cycle"
        )
        logger.warning(
            f"[process_refund] Unknown provider status {current_status_value!r} "
            f"for refund {refund.id}, skipping DB update, scheduler will check again in the next cycle"
        )
        return
    if new_db_status != RefundStatus.processed:
        print(
            f"[process_refund] Refund {refund.id} status is {new_db_status.value}, "
            f"not processed yet, scheduler will check again in the next cycle, skipping notification"
        )
        logger.info(
            f"[process_refund] Refund {refund.id} status is {new_db_status.value}, "
            f"not processed yet, scheduler will check again in the next cycle, skipping notification"
        )
        return
    if provider_refund_id != refund.id:
        refund.id = provider_refund_id  # Update the refund record's ID to match the provider refund ID if they differ
    refund.refund_status = new_db_status
    db.add(refund)
    await db.commit()
    await db.refresh(refund)

    trip = refund.trip
    if trip and trip.customer:
            await _send_refund_credited_notification(
                refund=refund,
                trip=trip,
                provider_refund_id=provider_refund_id,
            )
    else:
            logger.warning(
                f"[process_refund] Refund {refund.id} is processed but trip or "
                f"customer could not be loaded — skipping notification"
            )
            print(
                f"[process_refund] Refund {refund.id} is processed but trip or "
                f"customer could not be loaded — skipping notification"
            )
    print(f"[process_refund] Finished processing refund {refund.id}")
    logger.info(f"[process_refund] Finished processing refund {refund.id}")


async def _send_refund_credited_notification(
    refund: RefundORM, trip: Trip, provider_refund_id: str
):
    """
    Sends the 'Refund Credited' email once Razorpay confirms the refund is processed
    and the money is on its way to the customer's account.

    """
    try:
        with get_mysql_local_session() as sync_db:
            from core.config import settings

            config_store = settings.get_config_store(sync_db)
            decimal_places = (
                config_store.geographies.country_server.currency_decimal_places
            )
            currency = config_store.geographies.country_server.currency_symbol

        formatted_refund_amount = f"{refund.refund_amount:.{decimal_places}f}"
        formatted_original_amount = f"{trip.advance_payment:.{decimal_places}f}"
        customer = CustomerRead.model_validate(trip.customer)
        await notify_refund_processed_to_customer(
            customer=customer,
            refund_id=provider_refund_id,
            refund_amount=formatted_refund_amount,
            booking_id=trip.booking_id,
            currency=currency,
            original_amount=formatted_original_amount,
            refund_type=refund.refund_type.value if refund.refund_type else "full",
        )

        print(
            f"[process_refund] Sent refund processed notification for refund {refund.id} "
            f"(entity={refund.entity_id}) to customer {customer.id}"
        )
        logger.info(
            f"[process_refund] Sent refund processed notification for refund {refund.id} "
            f"(entity={refund.entity_id}) to customer {customer.id}"
        )

    except Exception as e:
        print(
            f"[process_refund] Failed to send refund-credited notification for "
            f"refund {refund.id}: {e}"
        )
        logger.error(
            f"[process_refund] Failed to send refund-credited notification "
            f"for refund {refund.id}: {e}"
        )


if __name__ == "__main__":
    # For local testing/debugging of the refund status sync task without running the entire scheduler
    asyncio.run(_run_refund_status_sync())
