from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Path
from core.security import validate_customer_token
from db.database import a_yield_mysql_session, yield_mysql_session
from models.customer.customer_orm import Customer
from models.driver.driver_schema import DriverRatingCreateSchema, DriverRatingSchema
from models.policies.refund_schema import RefundSchema
from models.trip.trip_enums import TripStatusEnum
from models.trip.trip_schema import (
    TripBookRequest,
    TripOut,
    TripSearchRequest,
)

from sqlalchemy.orm import Session

from services.driver_rating_service import save_driver_rating_for_trip_by_customer
from services.orchestration_service import BackgroundTaskOrchestrator
from services.refund_service import fetch_refund_detail_by_booking_id_and_customer_id
from services.trips.trip_service import get_trip_messages
from services.trips.booking_service import confirm_trip_booking, delete_temp_trip_by_booking_id, initiate_trip_booking
from services.trips.search_service import search
from utils.utility import remove_none_recursive
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post("/search")
def search_trip(
    search_in: TripSearchRequest,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):

    result= search(
        search_in=search_in, requestor=current_customer.id, db=db
    )
    return remove_none_recursive(result.model_dump())


@router.post("/initiate-booking", response_model=dict)
def init_booking(
    trip_in: TripBookRequest,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    trip_id, order =  initiate_trip_booking(
        booking_request=trip_in, customer=current_customer, db=db
    )

    return {
        "trip_id": trip_id, #This is the temp trip id created for the booking
        "order_id": order.get("id"),
        "amount": order.get("amount"),
        "currency": order.get("currency"),
        "description": order.get("description"),
        "customer":order.get("notes", {}).get("customer",{}),
        "status": order.get("status"),
        **get_trip_messages(status=TripStatusEnum.created),
    }


@router.post("/confirm-booking", response_model=dict)
def confirm_booking(
    booking: TripOut,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Confirm the trip booking after payment is successful.
    """
    created_trip=confirm_trip_booking(booking_request=booking, customer=current_customer, db=db)
    return {
        
        "booking_id": created_trip.booking_id,
        **get_trip_messages(status=TripStatusEnum.confirmed),
    }

@router.delete("/cleanup/{booking_id}", response_model=dict)
def cleanup_temp_trip_booking(
    booking_id: str,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Cleanup trip data for the customer.
    This endpoint is invoked silently from frontend when the customer abandons the trip search or payment page midway or payment fails.
    """ 
    is_deleted = delete_temp_trip_by_booking_id(booking_id=booking_id, requestor=current_customer.id, db=db)
    if is_deleted:
        return {"message": "Trip data cleaned up successfully."}
    return {"message": "Failed to clean up trip data."}

#Get endpoint for fetching refund details
@router.get("/refund/{booking_id}", response_model=RefundSchema)
async def get_refund_details(
    booking_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Fetch refund details for a specific booking.
    """
    refund_details = await fetch_refund_detail_by_booking_id_and_customer_id(booking_id=booking_id, requestor=current_customer.id, db=db)
    if not refund_details:
        raise HTTPException(status_code=404, detail="Refund details not found for the given booking ID.")
    return refund_details


# Route for providing driver rating and feedback for a trip by a customer
# Driver rating can be provided only once per trip by a customer for a driver. 1 trip -> 1 driver -> 1 rating by customer
@router.post("/{booking_id}/rate-driver")
async def rate_driver_for_trip(
    background_tasks: BackgroundTasks,

    payload: DriverRatingCreateSchema = Body(
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
    response, background_task = await save_driver_rating_for_trip_by_customer(
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