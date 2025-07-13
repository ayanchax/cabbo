from core.exceptions import CabboException
from models.trip.trip_orm import Trip, TripStatusAudit
from sqlalchemy.orm import Session
import logging

logger = logging.getLogger(__name__)


def log_trip_audit(trip: Trip, requestor: str, db: Session, commit: bool = True):
    """
    Function to log trip audit entries.
    Args:
        trip (Trip): The trip object for which the audit log is being created.
        requestor (str): The ID of the user or system that is logging the audit.
        db (Session): The database session to use for committing the audit log.
        commit (bool): Whether to commit the transaction after logging.
    Returns:
        None
    Raises:
        None

    """
    try:
        trip_audit_log = TripStatusAudit(
            trip_id=trip.id,
            status=trip.status,
            committer_id=requestor,
            reason="Trip confirmed for booking",
        )
        db.add(trip_audit_log)  # Add the trip audit log entry
        if commit:
            db.commit()
        db.refresh(trip_audit_log)
        print(f"Trip audit log created for trip ID: {trip.id} by {requestor}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log trip audit entry: {e}")
