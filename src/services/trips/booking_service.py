import secrets
import string
from core.store import ConfigStore
from core.trip_helpers import get_trip_type_by_trip_type_id
from models.customer.customer_orm import Customer
from models.financial.payments_schema import RazorPayPaymentResponse
from models.pricing.pricing_schema import Currency
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripBookRequest,
    TripCreate,
    TripOut,
)
from sqlalchemy.orm import Session
from models.trip.trip_enums import (
    TripStatusEnum,
)
from core.exceptions import CabboException
from services.audit_trail_service import log_trip_audit
from services.payment_service import (
    attach_trip_details_to_order_notes,
    get_trip_payment_order,
    verify_payment,
)
from services.trips.trip_service import (
    create_temporary_trip,
    delete_temp_trip,
    populate_trip_schema,
    verify_trip_hash,
)
from services.validation_service import (
    validate_booking_request,
)
from core.config import settings


def _generate_booking_id(trip_type: str, db: Session, length: int = 16, attempts: int = 5) -> str:
    """
    Generate a unique booking ID with a prefix based on the trip type.
    The ID will consist of a trip type prefix followed by a 16-character alphanumeric string.

    
    Args:
        trip_type (str): The type of trip (e.g., "AIRPORTTFR-PICKUP", "AIRPORTTFR-DROP", "OUTSTATION", "RENTAL").
        db (Session): The database session for ORM operations.
        length (int): The length of the unique part of the booking ID (default is 16).
        attempts (int): The maximum number of attempts to generate a unique ID in case of collisions (default is 5).
    
    Returns:
        str: The generated booking ID.
    """
    try:
        # Map trip types to prefixes
        trip_type_prefix = {
            "airport_pickup": "AIRPORTTFR-PICKUP",
            "airport_drop":"AIRPORTTFR-DROP",
            "outstation": "OUTSTATION",
            "local": "RENTAL"
        }.get(trip_type.lower(), "TRIP")  # Default to "TRIP" if trip type is unknown

        # Generate the unique part of the booking ID
        alphabet = string.ascii_uppercase + string.digits
        while True:
            unique_part = ''.join(  secrets.choice(alphabet) for _ in range(length))
            booking_id = f"{trip_type_prefix}-{unique_part}"
            exists=db.query(Trip).filter(Trip.booking_id == booking_id).first()
            if not exists:
                return booking_id
            attempts -= 1 # Decrement the attempts counter if a collision is found, to avoid infinite loop in case of high collision probability
            if attempts <= 0:
                return None  # Return None if maximum attempts are reached without generating a unique ID

    except Exception as e:
        return None
    
def _get_temp_trip_by_trip_id_and_requestor(
    trip_id: str, requestor: str, db: Session
) -> TempTrip:
    """
    Retrieves a temporary trip record from the database based on the trip ID and requestor.
    Args:
        trip_id (str): The ID of the trip to retrieve.
        requestor (str): The user or system requesting the trip details.
        db (Session): The database session for ORM operations.
    Returns:
        TempTrip: The retrieved temporary trip record.
    Raises:
        CabboException: If the trip is not found or if the requestor is not authorized to access it.
    """
    temp_trip = (
        db.query(TempTrip)
        .filter(TempTrip.id == trip_id, TempTrip.creator_id == requestor)
        .first()
    )
    if not temp_trip:
        raise CabboException(
            "Trip not found or you are not authorized to access this trip",
            status_code=404,
        )
    return temp_trip


def _is_existing_trip_booking(trip_id: str, requestor: str, db: Session) -> bool:
    """
    Checks if a trip booking exists in the database for the given trip ID and requestor.
    Args:
        trip_id (str): The ID of the trip to retrieve.
        requestor (str): The user or system requesting the trip details.
        db (Session): The database session for ORM operations.
    Returns:
        bool: True if the trip booking exists, False otherwise.
    """
    trip = (
        db.query(Trip)
        .filter(Trip.id == trip_id, Trip.creator_id == requestor)
        .first()
    )
    if trip:
        return True
    return False


def _create_confirmed_trip_from_temp_trip(
    temp_trip: TempTrip,
    requestor: str,
    payment_info: RazorPayPaymentResponse,
    db: Session,
) -> TripCreate:
    """Creates a confirmed trip record from a temporary trip record.
    This function takes a temporary trip record, validates it, and creates a confirmed trip record in the database.
    Args:
        temp_trip (TempTrip): The temporary trip record to convert.
        requestor (str): The user or system requesting the trip creation.
        payment_info (RazorPayPaymentResponse): The payment information for the trip.
        db (Session): The database session for ORM operations.
    Returns:
        TripCreate: The created confirmed trip record.
    Raises:
        CabboException: If the temporary trip is invalid or if any database operation fails.
    """
    trip_type = get_trip_type_by_trip_type_id(temp_trip.trip_type_id, db)
    if not trip_type:
        raise CabboException(
            f"Invalid trip type ID: {temp_trip.trip_type_id}", status_code=400
        )
    trip_type_name= str(trip_type.name)
    booking_id = _generate_booking_id(trip_type=trip_type_name.lower(), db=db)
    if not booking_id:
        raise CabboException(
            "Failed to generate booking ID", status_code=500
        )
    
    trip = Trip(
        id=temp_trip.id,
        booking_id = booking_id,
        creator_id=temp_trip.creator_id,
        creator_type=temp_trip.creator_type,
        trip_type_id=temp_trip.trip_type_id,
        origin=temp_trip.origin,
        destination=temp_trip.destination,
        hops=temp_trip.hops,
        is_interstate=temp_trip.is_interstate,
        is_round_trip=temp_trip.is_round_trip,
        total_unique_states=temp_trip.total_unique_states,
        unique_states=temp_trip.unique_states,
        package_id=temp_trip.package_id,
        package_label=temp_trip.package_label,
        package_label_short=temp_trip.package_label_short,
        start_datetime=temp_trip.start_datetime,
        end_datetime=temp_trip.end_datetime,
        expected_end_datetime=temp_trip.expected_end_datetime,
        total_days=temp_trip.total_days,
        included_kms=temp_trip.included_kms,
        num_adults=temp_trip.num_adults,
        num_children=temp_trip.num_children,
        num_passengers=temp_trip.num_passengers,
        num_large_suitcases=temp_trip.num_large_suitcases,
        num_carryons=temp_trip.num_carryons,
        num_backpacks=temp_trip.num_backpacks,
        num_other_bags=temp_trip.num_other_bags,
        num_luggages=temp_trip.num_luggages,
        preferred_car_type=temp_trip.preferred_car_type,
        preferred_fuel_type=temp_trip.preferred_fuel_type,
        in_car_amenities=(
            temp_trip.in_car_amenities if temp_trip.in_car_amenities else None
        ),
        price_breakdown=(
            temp_trip.price_breakdown if temp_trip.price_breakdown else None
        ),
        overages=temp_trip.overages if temp_trip.overages else None,
        base_fare=temp_trip.base_fare,
        driver_allowance=temp_trip.driver_allowance,
        tolls=temp_trip.tolls,
        parking=temp_trip.parking,
        permit_fee=temp_trip.permit_fee,
        platform_fee=temp_trip.platform_fee,
        final_price=temp_trip.final_price,
        final_display_price=temp_trip.final_display_price,
        advance_payment=temp_trip.platform_fee,
        balance_payment=temp_trip.final_price - temp_trip.platform_fee,
        status=TripStatusEnum.confirmed,
        inclusions=temp_trip.inclusions if temp_trip.inclusions else None,
        exclusions=temp_trip.exclusions if temp_trip.exclusions else None,
        flight_number=temp_trip.flight_number if temp_trip.flight_number else None,
        terminal_number=(
            temp_trip.terminal_number if temp_trip.terminal_number else None
        ),
        toll_road_preferred=(
            temp_trip.toll_road_preferred if temp_trip.toll_road_preferred else False
        ),
        placard_required=(
            temp_trip.placard_required if temp_trip.placard_required else False
        ),
        placard_name=temp_trip.placard_name if temp_trip.placard_name else None,
        estimated_km=temp_trip.estimated_km if temp_trip.estimated_km else 0.0,
        indicative_overage_warning=(
            temp_trip.indicative_overage_warning
            if temp_trip.indicative_overage_warning
            else None
        ),
        alternate_customer_phone=(
            temp_trip.alternate_customer_phone
            if temp_trip.alternate_customer_phone
            else None
        ),
        passenger_id=temp_trip.passenger_id if temp_trip.passenger_id else None,
        payment_provider_metadata=(
            payment_info.model_dump(exclude_none=True) if payment_info else None
        ),
    )

    try:
        db.add(trip)
        db.commit()
        db.refresh(trip)
        # Here we will perform a trip status audit log entry
        log_trip_audit(
            trip_id=trip.id,
            status=trip.status,
            committer_id=requestor,
            reason="Trip confirmed",
            db=db,
        )  # Log the trip status audit entry
        print(f"Trip confirmed for trip ID: {trip.id}")
        # After confirming the trip, delete the temporary(one or more) trip details for this customer
        delete_temp_trip(
            requestor=requestor, db=db
        )  # Clean up all temporary trip details for this customer.
        trip_schema = populate_trip_schema(
            trip=trip, db=db
        )  # Populate the trip schema with necessary details
        return TripCreate(
            trip_id=trip.id,
            booking_id=trip.booking_id,
            payment_info=payment_info,
            status=trip.status,
            trip_details=trip_schema,
        )

    except Exception as e:
        db.rollback()
        print(e)
        raise CabboException(
            f"Failed to confirm trip booking: {str(e)}", status_code=500
        )


def initiate_trip_booking(
    booking_request: TripBookRequest, customer: Customer, db: Session
):
    """
    Initiates a booking for a trip based on the provided booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing trip details.
        customer (Customer): The user or system initiating the booking.
        db (Session): The database session for ORM operations.
    Returns:
        TripBookResponse: The response containing booking details.
    Raises:
        CabboException: If the booking request is invalid or if any error occurs during booking.

    """
    try:
        # Verify the trip_in.option.hash, if not valid (tampered), raise exception and return error response
        verify_trip_hash(booking_request=booking_request)

        # Check for duplicate or conflicting bookings for the same customer.
        validate_booking_request(
            booking_request=booking_request, requestor=customer.id, db=db
        )

        # Delete all previous temporary trip details for the customer
        delete_temp_trip(requestor=customer.id, db=db)

        # Create a new Temp Trip object from the booking request
        temp_trip = create_temporary_trip(
            booking_request=booking_request, requestor=customer.id, db=db
        )

        config_store: ConfigStore = settings.get_config_store(db)
        currency:Currency = Currency(
            code=config_store.geographies.country_server.currency or "INR",
            symbol=config_store.geographies.country_server.currency_symbol or "₹",
        )
        # Create razor pay order for the trip
        trip_id, order = get_trip_payment_order(
            booking_request=booking_request, customer=customer, temp_trip=temp_trip, currency=currency
        )
        payment_provider_metadata= {
            "razorpay_order_id": order.get("id"),
            "amount": order.get("amount"),
            "currency": order.get("currency"),
            "receipt": order.get("receipt"),
        }
        #After successful order creation, update the temp trip with payment provider metadata
        temp_trip.payment_provider_metadata=payment_provider_metadata
        db.commit()
        db.refresh(temp_trip)
        

        # Populate the trip schema with necessary details
        trip_schema = populate_trip_schema(
            trip=temp_trip, db=db
        )  # Populate the trip schema with necessary details

        attach_trip_details_to_order_notes(
            order=order, trip_details=trip_schema
        )  # Attach trip details to order notes

        return trip_id, order
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Failed to initiate trip booking: {str(e)}", status_code=500
        )


def confirm_trip_booking(booking_request: TripOut, customer: Customer, db: Session):
    """
    Confirms a trip booking based on the provided booking request.
    Args:
        booking_request (TripBookingOut): The trip booking request containing trip details.
        customer (Customer): The user or system confirming the booking.
        db (Session): The database session for ORM operations.
    Returns:
        TripBookResponse: The response containing booking details.
    Raises:
        CabboException: If the booking request is invalid or if any error occurs during confirmation.

    """
    # Logic to confirm the booking based on booking_id
    # This would typically involve checking payment status and updating trip status
    # For now, we will just return a success message

    if not booking_request.trip_id:
        raise CabboException(
            "Booking Trip ID is required to confirm the booking", status_code=400
        )

    # Check if the booking request already exists in the main Trip table
    existing_trip = _is_existing_trip_booking(
        trip_id=booking_request.trip_id, requestor=customer.id, db=db
    )
    if existing_trip:
        raise CabboException("Booking already exists", status_code=400)

    # Check in database if the booking exists
    temp_trip = _get_temp_trip_by_trip_id_and_requestor(
        trip_id=booking_request.trip_id, requestor=customer.id, db=db
    )

    # Verify the payment details in the booking request
    payment_verified = verify_payment(payment_detail=booking_request.payment_info)
    if not payment_verified:
        raise CabboException("Payment verification failed", status_code=400)

    # If payment is verified, create a new Trip object from the TempTrip object and confirm the booking
    return _create_confirmed_trip_from_temp_trip(
        temp_trip=temp_trip,
        requestor=customer.id,
        payment_info=booking_request.payment_info,
        db=db,
    )


def delete_temp_trip_by_booking_id(booking_id: str, requestor: str, db: Session):
    """
    Deletes a temporary trip record from the database based on the booking ID and requestor.
    Args:
        booking_id (str): The ID of the booking to delete.
        requestor (str): The user or system requesting the deletion.
        db (Session): The database session for ORM operations.
    Raises:
        CabboException: If the trip is not found or if the requestor is not authorized to delete it.
    """
    temp_trip = (
        db.query(TempTrip)
        .filter(TempTrip.id == booking_id, TempTrip.creator_id == requestor)
        .first()
    )
    if not temp_trip:
        raise CabboException(
            "Booking not found or you are not authorized to delete this booking",
            status_code=404,
        )
    try:
        db.delete(temp_trip)
        db.commit()
        print(f"Temporary trip deleted for booking ID: {booking_id}")
        return True
    except Exception as e:
        db.rollback()
        return False
