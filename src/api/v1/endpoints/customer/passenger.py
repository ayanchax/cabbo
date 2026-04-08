from fastapi import (
    APIRouter,
    Depends,
    Path,
)
from sqlalchemy.orm import Session
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from models.customer.passenger_schema import (
    PassengerCreate,
    PassengerOut,
    PassengerUpdate,
)
from services.customer_service import (
    get_active_customer_by_id,
)

from core.security import validate_customer_token
from core.exceptions import CabboException
from services.passenger_service import (
    create_passenger,
    delete_passenger,
    is_passenger_belongs_to_customer,
    update_passenger,
)
from services.validation_service import (
    validate_passenger_payload,
)

router = APIRouter()

# Passenger management endpoints for customers to manage their passengers which they can then associate with their trip bookings. This will allow customers to easily manage the details of their passengers and associate them with their trips for a smoother booking experience. These endpoints will also validate the JWT token to ensure that only authenticated customers can manage their passengers and that they can only manage passengers associated with their own account for privacy and security reasons.


@router.post("/passenger/add", response_model=PassengerOut)
def add_passenger(
    payload: PassengerCreate = Depends(validate_passenger_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):

    customer_id = current_customer.id

    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException("Customer not found", status_code=404)
    passenger = create_passenger(customer_id, payload, db)
    if passenger is None:
        raise CabboException("Failed to create passenger", status_code=500)
    return PassengerOut.model_validate(passenger)


@router.delete("/passenger/{passenger_id}/remove")
def remove_passenger(
    passenger_id: str = Path(..., description="UUID of the passenger to remove"),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException("Customer not found", status_code=404)

    # ?We do not need this condition check because if a passenger is deleted and they are associated with one or more trip, then in trip.passenger_id it will automatically be nullified because of the foreign key constraint with ondelete set to null
    
    delete_passenger(passenger_id, db)
    return {"message": "Passenger removed successfully."}


@router.put("/passenger/{passenger_id}/update", response_model=PassengerOut)
def update_passenger_details(
    passenger_id: str = Path(..., description="UUID of the passenger to update"),
    payload: PassengerUpdate = Depends(validate_passenger_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id

    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException("Customer not found", status_code=404)
    passenger = update_passenger(passenger_id, payload, db)

    if passenger is None:
        raise CabboException("Failed to update passenger", status_code=500)
    return PassengerOut.model_validate(passenger)


@router.get("/", response_model=list[PassengerOut])
def list_passengers(
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id

    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException("Customer not found", status_code=404)
    from services.passenger_service import get_all_passengers_by_customer_id

    passengers = get_all_passengers_by_customer_id(customer_id, db)
    return [PassengerOut.model_validate(passenger) for passenger in passengers]


@router.get("/passenger/{passenger_id}", response_model=PassengerOut)
def get_passenger(
    passenger_id: str = Path(..., description="UUID of the passenger"),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException("Customer not found", status_code=404)

    passenger = is_passenger_belongs_to_customer(passenger_id, customer_id, db)
    if not passenger and isinstance(passenger, bool):
        raise CabboException("Passenger not found for this customer", status_code=404)

    return PassengerOut.model_validate(passenger)
