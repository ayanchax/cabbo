import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import AsyncSessionLocal
from models.trip.temp_trip_orm import TempTrip
from scheduler.task_registry import task
import logging

TTL_MINUTES_DEFAULT = 30
log = logging.getLogger(__name__)


@task(task_id="cleanup_temp_trips", description="Deletes expired temp trips older than TTL")
def cleanup_temp_trips_task(ttl_minutes: int = TTL_MINUTES_DEFAULT):
    asyncio.run(_run_cleanup_temp_trips(ttl_minutes=ttl_minutes))


async def _run_cleanup_temp_trips(ttl_minutes: int = TTL_MINUTES_DEFAULT):
    async with AsyncSessionLocal() as db:
        try:
            removed = await a_cleanup_expired_temp_trips(db=db, ttl_minutes=ttl_minutes)
            log.info(f"cleanup_temp_trips removed {removed} rows")
        except Exception:
            log.error("cleanup_temp_trips failed")


async def a_cleanup_expired_temp_trips(
    db: AsyncSession, ttl_minutes: int = TTL_MINUTES_DEFAULT
) -> int:
    """
    Deletes unpaid temp trips older than ttl_minutes.

    Payment-verified temp trips are intentionally preserved. They represent
    cases where Razorpay verification succeeded but Trip creation did not finish,
    and must be handled by a recovery job or admin workflow instead of cleanup.

    Returns number of rows deleted.
    """
    try:
        log.info(f"Running cleanup_expired_temp_trips with TTL={ttl_minutes} minutes")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        result = await db.execute(
            select(TempTrip).where(TempTrip.created_at < cutoff)
        )
        expired_temp_trips = result.scalars().all()

        removed = 0
        skipped_verified = 0
        for temp_trip in expired_temp_trips:
            metadata = temp_trip.payment_provider_metadata or {}
            if isinstance(metadata, dict) and metadata.get("payment_verified") is True:
                skipped_verified += 1
                continue

            await db.delete(temp_trip)
            removed += 1

        await db.commit()
        if skipped_verified:
            log.info(
                f"cleanup_temp_trips skipped {skipped_verified} payment-verified rows. Those will be upgraded to real trips using our admin workflows on demand."
            )
        log.info(f"cleanup_temp_trips removed {removed} abandoned rows.")
        return removed
    except Exception as e:
        await db.rollback()
        log.error(f"Error during cleanup_expired_temp_trips: {e}")
        return 0
