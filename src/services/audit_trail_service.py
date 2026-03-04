from sqlalchemy.orm import Session
from core.security import RoleEnum
from models.trip.trip_orm import TripStatusAudit
from models.trip.trip_enums import TripStatusEnum, CancellationSubStatusEnum
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

import logging

logger = logging.getLogger(__name__)

def log_trip_audit(
    db: Session,
    trip_id: str,
    status: TripStatusEnum,
    committer_id: str,
    reason: Optional[str] = None,
    cancellation_sub_status: Optional[CancellationSubStatusEnum] = None,
    commit: bool = True
):
    """
    Function to log trip status audit entries.
    Args:
        db (Session): The database session to use for committing the audit log.
        trip_id (str): The ID of the trip being audited.
        status (TripStatusEnum): The new status of the trip.
        committer_id (str): The ID of the user or system that is logging the audit.
        changed_by (Optional[RoleEnum]): The role of the user making the change.
        reason (Optional[str]): Reason for the status change, if applicable.
        cancellation_sub_status (Optional[CancellationSubStatusEnum]): Sub-status for cancellations, if applicable.
        commit (bool): Whether to commit the transaction after logging.
    Returns:
        TripStatusAudit: The created audit log entry.
    Raises:
        None
    """
    try:
        audit = TripStatusAudit(
            trip_id=trip_id,
            committer_id=committer_id,
            status=status,
            reason=reason,
            cancellation_sub_status=cancellation_sub_status,
        )
        db.add(audit)
        if commit:
            db.commit()
        db.refresh(audit)
        print(f"Trip audit log created for trip ID: {trip_id} by {committer_id}")
        return audit
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to log trip audit entry: {e}")


async def a_log_trip_audit(
    db: AsyncSession,
    trip_id: str,
    status: TripStatusEnum,
    committer_id: str,
    reason: Optional[str] = None,
    cancellation_sub_status: Optional[CancellationSubStatusEnum] = None,
    commit: bool = True
):
    """
    Function to log trip status audit entries.
    Args:
        db (Session): The database session to use for committing the audit log.
        trip_id (str): The ID of the trip being audited.
        status (TripStatusEnum): The new status of the trip.
        committer_id (str): The ID of the user or system that is logging the audit.
        changed_by (Optional[RoleEnum]): The role of the user making the change.
        reason (Optional[str]): Reason for the status change, if applicable.
        cancellation_sub_status (Optional[CancellationSubStatusEnum]): Sub-status for cancellations, if applicable.
        commit (bool): Whether to commit the transaction after logging.
    Returns:
        TripStatusAudit: The created audit log entry.
    Raises:
        None
    """
    try:
        audit = TripStatusAudit(
            trip_id=trip_id,
            committer_id=committer_id,
            status=status,
            reason=reason,
            cancellation_sub_status=cancellation_sub_status,
        )
        db.add(audit)
        await db.flush()  # Ensure the audit entry is added to the session before committing
        if commit:
            await db.commit()
            await db.refresh(audit)
        print(f"Trip audit log created for trip ID: {trip_id} by {committer_id}")
        return audit
    except Exception as e:
        await db.rollback()
        logger.error(f"Failed to log trip audit entry: {e}")
