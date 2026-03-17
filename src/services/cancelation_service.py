from typing import Optional

from core.security import RoleEnum
from models.policies.cancelation_orm import Cancellation
from models.policies.cancelation_schema import (
    CancelationPolicySchema,
    CancelationSchema,
)
from models.trip.trip_enums import CancellationSubStatusEnum
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


def get_cancelation_payload(
    cancelation_detail: Optional[CancelationSchema],
    trip_id: str,
    user_id: str,
    cancelation_sub_status: CancellationSubStatusEnum,
):
    cancelation_payload = cancelation_detail if cancelation_detail else None
    if not cancelation_payload:
        cancelation_payload = CancelationSchema(
            entity_id=trip_id,
            canceled_by=user_id,
            cancellation_sub_status=cancelation_sub_status,
            reason=(
                cancelation_detail.reason
                if cancelation_detail and cancelation_detail.reason
                else "No reason provided"
            ),
        )
    return cancelation_payload


def get_cancelation_sub_status(
    requestor: User,
    creator_id: str,
    cancelation_detail: Optional[CancelationSchema] = None,
):
    cancelation_sub_status = CancellationSubStatusEnum.other
    if requestor.role == RoleEnum.customer and requestor.id == creator_id:
        # Customer-initiated cancellation
        cancelation_sub_status = CancellationSubStatusEnum.customer_cancelled

    else:
        # System-initiated cancellation (e.g. due to customer no-show, driver cancellation, driver_unavailable, driver no-show etc.) or Admin-initiated cancellation
        cancelation_sub_status = (
            cancelation_detail.cancellation_sub_status
            if cancelation_detail and cancelation_detail.cancellation_sub_status
            else CancellationSubStatusEnum.other
        )

    return cancelation_sub_status


async def register_trip_cancellation(
    payload: CancelationSchema,
    db: AsyncSession,
    silently_fail: bool = False,
    commit: bool = True,
):
    try:
        existing_cancelation = await get_cancellation_by_trip_id(
            trip_id=payload.entity_id, db=db
        )
        if existing_cancelation:
            print(
                f"Existing cancellation record found for trip {payload.entity_id}, removing it before adding new cancellation details"
            )
            await remove_cancellation_by_trip_id(
                trip_id=payload.entity_id, db=db, hard_delete=True, commit=commit
            )

        return await _create_cancellation_record(
            payload=payload,
            db=db,
            silently_fail=silently_fail,
            commit=commit,
        )
    except Exception as e:
        print(f"Error registering cancellation for trip {payload.entity_id}: {e}")
        if not silently_fail:
            raise e
        return None


async def _create_cancellation_record(
    payload: CancelationSchema,
    db: AsyncSession,
    silently_fail: bool = False,
    commit: bool = True,
):
    """
    This function creates a cancellation record for a trip. It is called when a trip is marked as cancelled. The cancellation record is created with the details provided in the payload. If silently_fail is set to True, the function will not raise an exception if it fails to create a cancellation record.
    """
    try:
        new_cancellation = Cancellation(
            entity_id=payload.entity_id,
            canceled_by=payload.canceled_by,
            cancellation_sub_status=payload.cancellation_sub_status,
            reason=payload.reason,
        )
        db.add(new_cancellation)
        await db.flush()  # Flush to ensure the cancellation record is saved before any further operations
        if commit:
            await db.commit()
        await db.refresh(new_cancellation)
        return CancelationSchema.model_validate(new_cancellation)
    except Exception as e:
        await db.rollback()
        if not silently_fail:
            raise e
        return None


async def get_cancellation_by_trip_id(
    trip_id: str, db: AsyncSession
) -> Optional[CancelationSchema]:
    try:
        result = await db.execute(
            select(Cancellation).where(
                Cancellation.entity_id == trip_id, Cancellation.is_active == True
            )
        )
        cancellation = result.scalars().first()
        if cancellation:
            return CancelationSchema.model_validate(cancellation)
        return None
    except Exception as e:
        print(f"Error fetching cancellation record for trip_id {trip_id}: {e}")
        return None


async def remove_cancellation_by_trip_id(
    trip_id: str, db: AsyncSession, hard_delete: bool = False, commit: bool = True
):
    try:
        result = await db.execute(
            select(Cancellation).where(Cancellation.entity_id == trip_id)
        )
        cancellation = result.scalars().first()
        if cancellation:
            if hard_delete:
                await db.delete(cancellation)
            else:
                cancellation.is_active = False
                db.add(cancellation)
            if commit:
                await db.commit()
            return True
        return False
    except Exception as e:
        print(f"Error removing cancellation record for trip_id {trip_id}: {e}")
        await db.rollback()
        return False


def get_cancelation_policy_id(policy: Optional[CancelationPolicySchema]):

    if policy and policy.id:
        return policy.id

    return None
