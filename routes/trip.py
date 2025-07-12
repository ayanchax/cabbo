from fastapi import APIRouter, Depends
from core.security import validate_customer_token
from db.database import get_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_schema import (
    TripBookRequest,
    TripSearchRequest,
    TripSearchResponse,
)
from services.trip_service import get_trip_search_options, initiate_booking
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
    # Verify the trip_in.option.hash, if not valid (tampered), raise exception and return error response
    # Check for duplicate or conflicting bookings (optional, planned for future release)
    # Store the booking data (option, preferences, user info, hash, etc.) in a `temp_trips` (or `pending_trips`) table with a unique temp ID.
    # Create a Razorpay order for the platform fee (amount from option's price breakdown).
    # Return to frontend: `{ razorpay_order_id, amount, currency, temp_trip_id }`.
    initiate_booking(booking_request=trip_in, requestor=current_customer.id, db=db)
    return {
        "message": "Booking initiated successfully. Please complete the payment to confirm your booking."}


 
