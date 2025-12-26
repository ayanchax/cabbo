

from datetime import datetime, timedelta, timezone
import math
from core.exceptions import CabboException
# from models.geography.service_area_orm import ServiceableGeographyOrm
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
from models.trip.trip_orm import Trip, TripTypeMaster
from models.trip.trip_schema import TripBookRequest, TripDetails, TripSearchRequest
from services.location_service import get_state_from_location
from utils.utility import remove_none_recursive, transform_datetime_to_str, validate_date_time
from sqlalchemy.orm import Session


def _validate_duplicate_local_bookings(booking_request: TripBookRequest, requestor: str, db: Session, overlap_hours: int = 12):
        start_date = validate_date_time(date_time=booking_request.preferences.start_date)
       
        end_date = start_date + timedelta(hours=overlap_hours)  # Check for bookings within the next 12 hours
        existing_bookings = db.query(Trip).join(TripTypeMaster).filter(
            Trip.trip_type_id == TripTypeMaster.id,
            Trip.creator_id == requestor,
            Trip.start_datetime >= start_date,
            Trip.start_datetime <= end_date,
            Trip.status != TripStatusEnum.cancelled
        ).all()
        if existing_bookings:
            raise CabboException("You already have a booking for this time slot", status_code=400)

def _validate_duplicate_outstation_bookings(booking_request: TripBookRequest, requestor: str, db: Session):
        start_date = validate_date_time(date_time=booking_request.preferences.start_date)
        
        end_date = validate_date_time(date_time=booking_request.preferences.end_date)
        
        existing_bookings = (
            db.query(Trip)
            .join(TripTypeMaster)
            .filter(
                Trip.trip_type_id == TripTypeMaster.id,
                Trip.creator_id == requestor,
                Trip.status != TripStatusEnum.cancelled,
                Trip.start_datetime <= end_date,
                Trip.end_datetime >= start_date,
            )
            .all()
        )
        if existing_bookings:
            raise CabboException("You already have a booking for this time slot", status_code=400)

def _validate_airport_bookings(booking_request: TripBookRequest, requestor: str, db: Session, overlap_hours: int = 4):
        start_date = validate_date_time(date_time=booking_request.preferences.start_date)
        
        end_date = start_date + timedelta(hours=overlap_hours)  # Check for bookings within the next 6 hours
        existing_bookings = db.query(Trip).join(TripTypeMaster).filter(
            Trip.trip_type_id == TripTypeMaster.id,
            Trip.creator_id == requestor,
            Trip.start_datetime >= start_date,  
            Trip.start_datetime <= end_date,
            Trip.status != TripStatusEnum.cancelled
        ).all()
        if existing_bookings:
            raise CabboException("You already have a booking for this time slot", status_code=400)

def _validate_booking_request_hash(booking_request: TripBookRequest, requestor: str, db: Session):
    if not booking_request.option.hash:
        raise CabboException("Booking request must have a unique hash", status_code=400)
    
    if booking_request.option.hash:
        existing_temp_trip = db.query(TempTrip).filter(
            TempTrip.hash == booking_request.option.hash,
            TempTrip.creator_id == requestor,
        ).first()
        if existing_temp_trip:
            trip_schema=TripDetails.model_validate(existing_temp_trip)
            result= trip_schema.model_dump(exclude_none=True)  # Return the trip schema as a dictionary excluding None values
            trip_details=remove_none_recursive(result)
            trip_details = transform_datetime_to_str(trip_details)
            raise CabboException({"message":"You already have made a similar booking which is incomplete. Please complete the previous booking to continue", "incomplete_trip_details":trip_details}, status_code=400)
    
def validate_booking_request(booking_request: TripBookRequest, requestor: str, db: Session):
    #case 0: Check if the booking request is a valid request with an unique hash
    _validate_booking_request_hash(booking_request=booking_request, requestor=requestor, db=db)
    
    #Check conflicting bookings on the same time range for the same customer based on trip type

    # case 1: If the trip is local, check for existing bookings for the same customer with the same start date within the next 24 hours
    
    if booking_request.preferences.trip_type == TripTypeEnum.local:
        _validate_duplicate_local_bookings(booking_request=booking_request, requestor=requestor, db=db)
    
    # case 2: If the trip is outstation, check for existing bookings for the same customer between the start and end dates

    elif booking_request.preferences.trip_type == TripTypeEnum.outstation:
        _validate_duplicate_outstation_bookings(booking_request=booking_request, requestor=requestor, db=db)
    
    # case 3: If the trip is airport pickup or drop, check for existing bookings for the same customer with the same start date within the next 6 hours
    elif booking_request.preferences.trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        _validate_airport_bookings(booking_request=booking_request, requestor=requestor, db=db)

    else:
        raise CabboException(f"Trip type {booking_request.preferences.trip_type} is not supported for booking", status_code=501)

def validate_serviceable_area(search_in: TripSearchRequest, db: Session):
    """
    Validates if the trip search request is within the serviceable area for the given trip type.
    Raises CabboException if the request is outside the serviceable area.
    """
    pass
    trip_type = search_in.trip_type
    # Query the serviceable area config for this trip type
    service_area = db.query(ServiceableGeographyOrm).join(
        TripTypeMaster, ServiceableGeographyOrm.trip_type_id == TripTypeMaster.id
    ).filter(ServiceableGeographyOrm.trip_type_id == TripTypeMaster.id, TripTypeMaster.trip_type==trip_type).first()
    if not service_area:
        raise CabboException(f"Serviceable area not configured for trip type: {trip_type}", status_code=500)

    # For local and airport trips, check city/airport
    if trip_type in [TripTypeEnum.local, TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        city_names = service_area.service_area_region_names or []
        
        if not city_names:
            raise CabboException(
                f"Serviceable cities not configured for trip type: {trip_type}",
                status_code=500,
            )
        airport_place_ids = service_area.airport_place_ids or []
        # For local: check origin city
        if trip_type == TripTypeEnum.local:
            if not search_in.origin:
                raise CabboException("Origin is required for local trip", status_code=400)
            origin_city = getattr(search_in.origin, 'display_name', '').lower()
            message = f"Local trips are only serviceable in: {', '.join(city_names)}"
            context = f"The city '{origin_city}' you have selected for local trip is not serviceable, try again with a different city."
            if not any(city.lower() in origin_city for city in city_names):
                raise CabboException({
                    "message": message,
                    "context": context,
                }, status_code=400)
        
        #For airport drop, check origin city
        elif trip_type == TripTypeEnum.airport_drop:
            if not airport_place_ids:
                raise CabboException(
                    "Airport place IDs not configured for airport drop trips",
                    status_code=500,
                )
            if not search_in.origin:
                raise CabboException("Origin is required for airport drop", status_code=400)
            origin_city = getattr(search_in.origin, 'display_name', '').lower()
            if not any(city.lower() in origin_city for city in city_names):
                message = f"Airport drop trips are only serviceable in: {', '.join(city_names)}"
                context = f"The city '{origin_city}' you have selected for airport drop is not serviceable, try again with a different city."
                raise CabboException({
                    "message": message,
                    "context": context,
                }, status_code=400)
            airport_place_id = getattr(search_in.destination, 'place_id', None)
            if airport_place_id is not None and airport_place_id not in airport_place_ids:
                raise CabboException(f"Airport drop trips are only serviceable to: {', '.join(airport_place_ids)}", status_code=400)
        
        #For airport pickup, check destination city
        elif trip_type == TripTypeEnum.airport_pickup:
            if not airport_place_ids:
                raise CabboException(
                    "Airport place IDs not configured for airport pickup trips",
                    status_code=500,
                )
            if not search_in.destination:
                raise CabboException("Destination is required for airport pickup", status_code=400)
            dest_city = getattr(search_in.destination, 'display_name', '').lower()
            if not any(city.lower() in dest_city for city in city_names):
                message = f"Airport pickup trips are only serviceable in: {', '.join(city_names)}"
                context = f"The city '{dest_city}' you have selected for airport pickup is not serviceable, try again with a different city."
                raise CabboException({
                    message: message,
                   "context": context,
                    }, status_code=400)
            airport_place_id = getattr(search_in.origin, 'place_id', None)
            if airport_place_id is not None and airport_place_id not in airport_place_ids:
                raise CabboException(f"Airport pickup trips are only serviceable from: {', '.join(airport_place_ids)}", status_code=400)
        
    # For outstation, check state codes
    elif trip_type == TripTypeEnum.outstation:
        if not search_in.origin or not search_in.destination:
            raise CabboException("Origin and destination are required for outstation trip", status_code=400)
        origin_state = get_state_from_location(location=search_in.origin, state_code=True)
        allowed_states = service_area.service_area_state_codes or []
        if not origin_state:
            raise CabboException(f"This location is not servicable yet", status_code=400)
        if origin_state not in allowed_states:
            message = f"Outstation trips are only serviceable from: {', '.join(allowed_states)}"
            context = f"The origin state '{origin_state}' you have selected for outstation trip is not serviceable, try again with a different state."
            raise CabboException({
                "message": message,
                "context": context,
            }, status_code=400)
        dest_state = get_state_from_location(location=search_in.destination, state_code=True)
        if not dest_state:
            raise CabboException(f"This location is not servicable yet", status_code=400)
        if dest_state not in allowed_states:
                message = f"Outstation trips are only serviceable to: {', '.join(allowed_states)}"
                context = f"The destination state '{dest_state}' you have selected for outstation trip is not serviceable, try again with a different state."
                raise CabboException({
                    "message": message,
                    "context": context,
                }, status_code=400)
        if search_in.hops:
            invalid_hops = []
            for hop in search_in.hops:
                hop_state = get_state_from_location(location=hop, state_code=True)
                if not hop_state:
                    continue # Skip if state cannot be determined
                if hop_state not in allowed_states:
                    invalid_hops.append(hop_state)
            if invalid_hops:
                message = (
                    f"Outstation trips are only serviceable to: {', '.join(allowed_states)}."
                )
                context = f"One or more hops in your trip is not serviceable: {', '.join(invalid_hops)}, try again with different hops within serviceable states or remove them."
                raise CabboException(
                    {
                        "message": message,
                        "context": context,
                    },
                    status_code=400,
                )
                    
    else:
        # If the trip type is not supported, raise an exception
        raise CabboException(f"Trip type {trip_type} is not supported", status_code=501)
    
    print(f"Trip search request is within serviceable area for trip type: {trip_type}")

def validate_placard_requirements(search_in: TripSearchRequest):
    """
    Validates the placard requirements for airport pickup trips.

    If the trip type is airport pickup and placard is required, it checks if the placard name is provided.
    Raises a CabboException if the placard name is missing.

    Args:
        search_in (TripSearchRequest): The trip search request object containing trip details.

    Raises:
        CabboException: If placard name is required but not provided.
    """
    if (
        search_in.trip_type == TripTypeEnum.airport_pickup
        and search_in.placard_required
        and not search_in.placard_name
    ):
        raise CabboException(
            "Placard name is required for airport pickup with placard",
            status_code=400,
        )


def validate_local_trip_schedule(search_in: TripSearchRequest):
    """
    Validates the start date and end date for local trips.
    Ensures that:
    - Start date is provided
    - Start date is not in the past
    - Start date is at least 3 hours from now
    Args:
        search_in (TripSearchRequest): The trip search request containing start date.
    Raises:
        CabboException: If any validation fails, with appropriate error messages.
    """
    if search_in.start_date is None:
        raise CabboException("Start date is required for local trip", status_code=400)
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date)

    now = datetime.now(timezone.utc)
    

    # Check for past dates
    if start_date < now:
        raise CabboException(
            "Start date for local trip cannot be in the past.", status_code=400
        )
    # Start date must be at least 6 hours after now
    min_start = now + timedelta(hours=6)
    if start_date < min_start:
        raise CabboException(
            "Start date for local trip must be at least 6 hours from now.",
            status_code=400,
        )


def validate_outstation_trip_schedule(search_in: TripSearchRequest):
    """
    Validates the start and end dates for outstation trips.
    Ensures that:
    - Start date and end date are provided
    - Dates are not in the past
    - Start date is at least 2 days from now
    - Start date is before end date
    - Total trip days are greater than 1
    Args:
        search_in (TripSearchRequest): The trip search request containing start and end dates.
        Returns:
        int: The total number of trip days (inclusive).
    Raises:
        CabboException: If any validation fails, with appropriate error messages.
    """
    if search_in.start_date is None or search_in.end_date is None:
        raise CabboException(
            "Start date and end date are required for outstation trip", status_code=400
        )
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date)
    
    end_date = validate_date_time(date_time=search_in.end_date)
    

    now = datetime.now(timezone.utc)
    

    # Check for past dates
    if start_date < now or end_date < now:
        raise CabboException(
            "Start date and end date for outstation trip cannot be in the past.",
            status_code=400,
        )
    # Start date must be at least 2 days after now
    min_start = now + timedelta(days=2)
    if start_date < min_start:
        raise CabboException(
            "Start date for outstation trip must be at least 2 days from now.",
            status_code=400,
        )
    if start_date > end_date:
        raise CabboException(
            "Start date cannot be after end date for outstation trip", status_code=400
        )
    # Calculate total number of trip days (inclusive, ceil if fractional)
    total_seconds = (end_date - start_date).total_seconds()
    total_days = math.ceil(total_seconds / 86400)
    if total_days <= 1:
        raise CabboException(
            "Total trip days must be greater than 1 for outstation trips",
            status_code=400,
        )
    return total_days


def validate_airport_schedule(search_in: TripSearchRequest):

    if search_in.start_date is None:
        raise CabboException(
            "Start date is required for airport transfer", status_code=400
        )
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date)

    now = datetime.now(timezone.utc)
    
    
    print(f"Current time (UTC): {now}")
    print(f"Start date (UTC): {start_date}")
    

    # Check for past dates
    if start_date < now:
        raise CabboException(
            "Start date for airport transfer cannot be in the past.",
            status_code=400,
        )
    # Start date must be at least 3 hours after now
    min_start = now + timedelta(hours=3)
    if start_date < min_start:
        raise CabboException(
            "Start date for airport trip must be at least 3 hours from now.",
            status_code=400,
        )
