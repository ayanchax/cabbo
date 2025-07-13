from fastapi import APIRouter, Depends
from core.security import validate_customer_token
from db.database import get_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_schema import (
    TripBookRequest,
    TripOut,
    TripSearchRequest,
    TripSearchResponse,
)
from services.trip_service import confirm_trip_booking, get_trip_search_options, initiate_trip_booking
from sqlalchemy.orm import Session

router = APIRouter(prefix="/trip", tags=["Trip"])


@router.post("/search", response_model=TripSearchResponse)
def search_trip(
    search_in: TripSearchRequest,
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
     
    return get_trip_search_options(
        search_in=search_in, requestor=current_customer.id, db=db
    )


@router.post("/initiate-booking", response_model=dict)
def init_booking(
    trip_in: TripBookRequest,
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    booking_id, order = initiate_trip_booking(booking_request=trip_in, customer=current_customer,  db=db)
    
    return {
        "booking_id": booking_id,
        "order_id": order.get("id"),
        "order": order,
        "message": "Booking initiated successfully. Please complete the payment to confirm your booking."}


@router.post("/confirm-booking", response_model=dict)
def confirm_booking(
    booking: TripOut,
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Confirm the trip booking after payment is successful.
    """
    
    trip_create_response=confirm_trip_booking(booking_request=booking, customer=current_customer, db=db)
    return {"message": "Booking confirmed successfully", "booking_id": booking.booking_id, **trip_create_response.model_dump()}
 
