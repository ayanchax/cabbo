from sqlalchemy.orm import Session
from core.security import RoleEnum
from models.trip.trip_orm import TripStatusAudit
from models.trip.trip_enums import TripStatusEnum, CancellationSubStatusEnum
from typing import Optional


def log_trip_status_audit(
    db: Session,
    trip_id: str,
    status: TripStatusEnum,
    committer_id: str,
    changed_by: Optional[RoleEnum] = RoleEnum.customer,
    reason: Optional[str] = None,
    cancellation_sub_status: Optional[CancellationSubStatusEnum] = None,
    responsible_preference_keys_for_cancelation: Optional[str] = None,
):
    """
    Logs a new trip status change in the TripStatusAudit table.
    Always inserts a new record (never updates), preserving a full audit trail.

    Args:
        db (Session): SQLAlchemy DB session
        trip_id (str): Trip UUID
        status (TripStatusEnum): New status
        changed_by (str): Actor (e.g., 'customer', 'admin', etc.)
        reason (str, optional): Reason or message for audit
        cancellation_sub_status (CancellationSubStatusEnum, optional): Detailed cancellation reason
        responsible_preference_keys_for_cancelation (str, optional): Snapshot of preference keys/flags (if any)
    """
    audit = TripStatusAudit(
        trip_id=trip_id,
        committer_id=committer_id,
        status=status,
        changed_by=changed_by,
        reason=reason,
        cancellation_sub_status=cancellation_sub_status,
        responsible_preference_keys_for_cancelation=responsible_preference_keys_for_cancelation,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit
