from fastapi import APIRouter, Depends
from core.security import validate_customer_token
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_enums import TripStatusEnum
from models.trip.trip_schema import (
    TripBookRequest,
    TripOut,
    TripSearchRequest,
    TripSearchResponse,
)

from sqlalchemy.orm import Session

from services.trips.trip_service import get_trip_messages
from services.trips.booking_service import confirm_trip_booking, delete_temp_trip_by_booking_id, initiate_trip_booking
from services.trips.search_service import search
from utils.utility import remove_none_recursive

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
    booking_id, order =  initiate_trip_booking(
        booking_request=trip_in, customer=current_customer, db=db
    )

    return {
        "booking_id": booking_id,
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
    _=confirm_trip_booking(booking_request=booking, customer=current_customer, db=db)
    return {
        
        "booking_id": booking.booking_id,
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




    