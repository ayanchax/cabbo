

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
    trip_type = search_in.trip_type
    pickup= search_in.origin
    
    if not pickup:
        raise CabboException("Pickup location is required", status_code=400)
    
    drop= search_in.destination
    if trip_type in [TripTypeEnum.local, TripTypeEnum.airport_drop, TripTypeEnum.airport_pickup]:
        #Local and airport trips are serviceable only within the city/region
        if trip_type == TripTypeEnum.local:
             if not drop:
                drop=pickup  #For local trips, consider drop as origin if not provided for service area check
        
        if trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]: #Pickup from airport to destination
            #For airport pickup, if drop is not provided, raise error
            if not drop:
                raise CabboException("Destination location is required for airport pickup or airport drop", status_code=400)
        
         


           

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
