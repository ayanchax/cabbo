from typing import Optional

from models.policies.dispute_enum import DisputeTypeEnum
from models.policies.dispute_schema import InitialDisputeSchema
from models.support.support_schema import SupportCommentSchema
from models.trip.trip_schema import TripDetailSchema
from sqlalchemy.ext.asyncio import AsyncSession
from models.policies.dispute_orm import Dispute as DisputeORM
from models.policies.dispute_schema import DisputeSchema
from sqlalchemy import select



async def create_dispute_record_for_trip(
    trip: TripDetailSchema,
    payload: Optional[InitialDisputeSchema],
    db: AsyncSession,
    requestor: str,
    silently_fail: bool = False,
):
    """
    This function creates a dispute record for a trip. It is called when a trip is marked as disputed. The dispute record is created with the initial details provided in the payload. If the payload is not provided, the dispute record is created with default values. The requestor parameter indicates who is creating the dispute (customer, driver, or admin). If silently_fail is set to True, the function will not raise an exception if it fails to create a dispute record.
    """
    try:
        comments = []
        if payload and payload.comments and isinstance(payload.comments, list):
            for comment in payload.comments:
                if isinstance(comment, SupportCommentSchema):
                    comment = comment.model_dump(exclude_unset=True, exclude_none=True)
                    comments.append(comment)
                elif isinstance(comment, dict):
                    comments.append(comment)
                else:
                    continue

        new_dispute = DisputeORM(
            entity_id=trip.id,
            reason=(
                payload.reason if payload and payload.reason else "No reason provided"
            ),
            dispute_type=(
                payload.dispute_type
                if payload and payload.dispute_type
                else DisputeTypeEnum.unknown
            ),
            comments=comments,
            details=payload.details if payload and payload.details else None,
            raised_by=requestor,
        )
        db.add(new_dispute)
        await db.flush()
        from services.trips.trip_service import async_get_trip_by_id
        trip_model= await async_get_trip_by_id(trip_id=trip.id, db=db)  # Refresh trip data to reflect the new dispute association
        if not trip_model:
                print(f"Trip not found with id {trip.id} while creating dispute record.")
                return None
        trip_model.dispute_id = new_dispute.id  # Associate the dispute with the trip
        await db.commit()
        await db.refresh(new_dispute)

        
        return DisputeSchema.model_validate(new_dispute)
    except Exception as e:
        await db.rollback()
        if silently_fail:
            return None
        else:
            raise e


async def get_dispute_by_trip_id(
    trip_id: str, db: AsyncSession
) -> Optional[DisputeSchema]:
    result = await db.execute(
        select(DisputeORM).where(
            DisputeORM.entity_id == trip_id, DisputeORM.is_active == True
        )
    )
    dispute_record = result.scalars().first()
    if dispute_record:
        return DisputeSchema.model_validate(dispute_record)
    return None
