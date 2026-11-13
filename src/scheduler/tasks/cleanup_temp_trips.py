import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from db.database import ASYNC_DATABASE_URL, ASYNC_CONNECT_ARGS
from models.trip.temp_trip_orm import TempTrip
from scheduler.task_registry import task
from services.trips.temp_trip_service import preserve_temp_trip
import logging
from core.config import settings

TTL_MINUTES_DEFAULT = 30
log = logging.getLogger(__name__)


@task(task_id="cleanup_temp_trips", description="Deletes expired temp trips older than TTL")
def cleanup_temp_trips_task(ttl_minutes: int = TTL_MINUTES_DEFAULT):
    asyncio.run(_run_cleanup_temp_trips(ttl_minutes=ttl_minutes))


async def _run_cleanup_temp_trips(ttl_minutes: int = TTL_MINUTES_DEFAULT):
    # Each scheduler invocation has its own loop; connections must stay on it.
    engine = create_async_engine(ASYNC_DATABASE_URL, connect_args=ASYNC_CONNECT_ARGS)
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with sessions() as db:
            removed = await a_cleanup_expired_temp_trips(db=db, ttl_minutes=ttl_minutes)
            log.info(f"cleanup_temp_trips removed {removed} rows")
    except Exception:
        log.exception("cleanup_temp_trips failed")
    finally:
        await engine.dispose()


async def a_cleanup_expired_temp_trips(
    db: AsyncSession, ttl_minutes: int = TTL_MINUTES_DEFAULT
) -> int:
    """
    Deletes temp trips without payment references older than ttl_minutes.

    Payment-linked temp trips are preserved even without a checkout callback.
    They must be reconciled before their booking details can be discarded.

    Returns number of rows deleted.
    """
    try:
        log.info(f"Running cleanup_expired_temp_trips with TTL={ttl_minutes} minutes")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        result = await db.execute(
            select(TempTrip).where(TempTrip.created_at < cutoff).with_for_update()
        )
        expired_temp_trips = result.scalars().all()

        removed = 0
        skipped_verified = 0
        for temp_trip in expired_temp_trips:
            metadata = temp_trip.payment_provider_metadata or {}
            if preserve_temp_trip(metadata):
                skipped_verified += 1
                continue

            await db.delete(temp_trip)
            removed += 1

        await db.commit()
        if skipped_verified:
            log.info(
                f"cleanup_temp_trips preserved {skipped_verified} payment-linked rows pending reconciliation."
            )
        log.info(f"cleanup_temp_trips removed {removed} abandoned rows.")
        next_scheduler_run = datetime.now(timezone.utc) + timedelta(minutes=settings.CLEANUP_TEMP_TRIPS_INTERVAL_MINUTES)
        log.info(f"Next scheduler run: {next_scheduler_run}")
        
        return removed
    except Exception as e:
        await db.rollback()
        log.error(f"Error during cleanup_expired_temp_trips: {e}")
        return 0
