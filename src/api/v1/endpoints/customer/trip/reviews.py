from fastapi import APIRouter, BackgroundTasks, Body, Depends, Path
from core.security import validate_customer_token
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_schema import (
    TripRatingCreateSchema,
    TripRatingResponseSchema,
)


from services.trip_review_service import (
    fetch_trip_review_by_booking_id_customer_id,
    save_trip_review,
)
from services.orchestration_service import BackgroundTaskOrchestrator
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# Route for providing trip rating and feedback by a customer
# Trip rating can be provided only once per trip by a customer 1 trip -> 1 rating by customer
@router.post("/{booking_id}/submit-review")
async def submit_trip_review(
    background_tasks: BackgroundTasks,
    payload: TripRatingCreateSchema = Body(
        ...,
        description="Rating, feedback and overall experience for the driver for the trip",
    ),
    booking_id: str = Path(
        ...,
        description="Unique identifier for the trip booking for which the driver is being rated",
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    response, background_task = await save_trip_review(
        booking_id=booking_id, customer_id=current_customer.id, payload=payload, db=db
    )
    if background_task:
        orchestrator = BackgroundTaskOrchestrator(background_tasks)
        orchestrator.add_task(
            background_task.fn,
            task_name=f"BackgroundTaskUpdateDriverAvgRating",
            **background_task.kwargs,
        )
    return response


# Get own review given for a trip.
@router.get(
    "/{booking_id}/review",
    response_model=TripRatingResponseSchema,
)
async def get_trip_review(
    booking_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """Get the review given by the current customer to a driver for a specific trip."""
    return await fetch_trip_review_by_booking_id_customer_id(
        booking_id=booking_id, customer_id=current_customer.id, db=db
    )
