from fastapi import APIRouter, Depends
from core.security import validate_customer_token
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_enums import TripStatusEnum
from models.trip.trip_schema import (
    TripBookRequest,
    TripOut,
    TripSearchRequest,
)

from sqlalchemy.orm import Session

from services.trips.trip_service import get_trip_messages
from services.trips.booking_service import (
    confirm_trip_booking,
    delete_temp_trip_by_booking_id,
    initiate_trip_booking,
)
from services.trips.search_service import search
from utils.utility import remove_none_recursive
from .reviews import router as trip_reviews
from .refunds import router as trip_refunds

router = APIRouter()


# Trip booking endpoints for customers to search for trips, initiate trip bookings, confirm trip bookings after payment and cleanup trip data for abandoned trips. These endpoints will validate the JWT token to ensure that only authenticated customers can access these functionalities and manage their trips securely. The search endpoint will allow customers to search for available trips based on their preferences and criteria, while the booking endpoints will handle the initiation and confirmation of trip bookings, as well as cleanup of trip data for abandoned or failed bookings to maintain data integrity and optimize storage. Additionally, there is an endpoint for fetching refund details for a specific booking, which will allow customers to view the status and details of their refunds in case of cancellations or other issues with their trips.


@router.post("/search")
def search_trip(
    search_in: TripSearchRequest,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):

    result = search(search_in=search_in, requestor=current_customer.id, db=db)
    return remove_none_recursive(result.model_dump())


@router.post("/initiate-booking", response_model=dict)
def init_booking(
    trip_in: TripBookRequest,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    trip_id, order = initiate_trip_booking(
        booking_request=trip_in, customer=current_customer, db=db
    )

    return {
        "trip_id": trip_id,  # This is the temp trip id created for the booking
        "order_id": order.get("id"),
        "amount": order.get("amount"),
        "currency": order.get("currency"),
        "description": order.get("description"),
        "customer": order.get("notes", {}).get("customer", {}),
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
    created_trip = confirm_trip_booking(
        booking_request=booking, customer=current_customer, db=db
    )
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
    is_deleted = delete_temp_trip_by_booking_id(
        booking_id=booking_id, requestor=current_customer.id, db=db
    )
    if is_deleted:
        return {"message": "Trip data cleaned up successfully."}
    return {"message": "Failed to clean up trip data."}


#Trip review endpoints for customers to provide ratings and feedback for their trips and view their reviews. These endpoints will validate the JWT token to ensure that only authenticated customers can access these functionalities and manage their trip reviews securely. The review endpoint will allow customers to submit their ratings and feedback for their completed trips, while the view reviews endpoint will enable customers to view their submitted reviews, enhancing the overall user experience and enabling better service quality through customer feedback.
router.include_router(
    trip_reviews, prefix="/reviews", tags=["customer-trip-review-management"]
)

#Trip refund endpoints for customers to fetch refund details for their bookings. This will allow customers to view the status and details of their refunds in case of cancellations or other issues with their trips. This endpoint will validate the JWT token to ensure that only authenticated customers can access their refund details securely.
router.include_router(
    trip_refunds, prefix="/refunds", tags=["customer-trip-refund-management"]
)
