from datetime import datetime, timedelta, timezone
from sqlalchemy import delete
from sqlalchemy.orm import Session
from db.database import get_mysql_local_session
from models.trip.temp_trip_orm import TempTrip
from scheduler.task_registry import task

TTL_MINUTES_DEFAULT = 30

@task(task_id="cleanup_temp_trips", description="Deletes expired temp trips older than TTL")
def cleanup_temp_trips_task(ttl_minutes: int = TTL_MINUTES_DEFAULT):
    with get_mysql_local_session() as db:
        try:
            removed = _cleanup_expired_temp_trips(db=db, ttl_minutes=ttl_minutes)
            print(f"cleanup_temp_trips removed {removed} rows")
        except Exception:
            print("cleanup_temp_trips failed")

def _cleanup_expired_temp_trips(db: Session, ttl_minutes: int = TTL_MINUTES_DEFAULT) -> int:
    """
    Deletes temp trips older than ttl_minutes
    Returns number of rows deleted.
    """
    try:
        print(f"Running cleanup_expired_temp_trips with TTL={ttl_minutes} minutes")
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=ttl_minutes)
        stmt = (
            delete(TempTrip)
            .where(TempTrip.created_at < cutoff)
        )
        res = db.execute(stmt)
        db.commit()
        return res.rowcount
    except Exception as e:
        db.rollback()
        print(f"Error during cleanup_expired_temp_trips: {e}")
        return 0
        # Wont raise further, as this is a cleanup task
