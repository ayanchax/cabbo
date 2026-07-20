from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from db.database import get_mysql_local_session
from models.trip.temp_trip_orm import TempTrip
from scheduler.task_registry import task
import logging
TTL_MINUTES_DEFAULT = 30
log = logging.getLogger(__name__)
@task(task_id="cleanup_temp_trips", description="Deletes expired temp trips older than TTL")
def cleanup_temp_trips_task(ttl_minutes: int = TTL_MINUTES_DEFAULT):
    with get_mysql_local_session() as db:
        try:
            removed = _cleanup_expired_temp_trips(db=db, ttl_minutes=ttl_minutes)
            log.info(f"cleanup_temp_trips removed {removed} rows")
        except Exception:
            log.error("cleanup_temp_trips failed")

def _cleanup_expired_temp_trips(db: Session, ttl_minutes: int = TTL_MINUTES_DEFAULT) -> int:
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
        expired_temp_trips = (
            db.query(TempTrip)
            .filter(TempTrip.created_at < cutoff)
            .all()
        )

        removed = 0
        skipped_verified = 0
        for temp_trip in expired_temp_trips:
            metadata = temp_trip.payment_provider_metadata or {}
            if isinstance(metadata, dict) and metadata.get("payment_verified") is True:
                skipped_verified += 1
                continue

            db.delete(temp_trip)
            removed += 1

        db.commit()
        if skipped_verified:
            log.info(
                f"cleanup_temp_trips skipped {skipped_verified} payment-verified rows. Those will be upgraded to real trips using our scheduled workflows or admin endpoints."
            )
        log.info(f"cleanup_temp_trips removed {removed} abandoned rows.")
        return removed
    except Exception as e:
        db.rollback()
        log.error(f"Error during cleanup_expired_temp_trips: {e}")
        return 0
