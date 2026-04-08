from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import List, Union

from fastapi import Body
from core.exceptions import CabboException
from core.config import settings

# from models.geography.service_area_orm import ServiceableGeographyOrm
from core.store import ConfigStore
from db.database import get_mysql_local_session
from models.airport.airport_schema import AirportSchema
from models.customer.customer_schema import CustomerCreate, CustomerLoginRequest, CustomerOnboardInitiationRequest, CustomerUpdate
from models.customer.passenger_schema import PassengerCreate, PassengerUpdate
from models.driver.driver_schema import DriverCreateSchema, DriverUpdateSchema
from models.geography.country_schema import CountrySchema
from models.map.location_schema import LocationInfo
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
from models.trip.trip_orm import Trip, TripTypeMaster
from models.trip.trip_schema import TripBookRequest, TripDetails, TripSearchRequest
from models.user.user_schema import UserCreateSchema, UserUpdateSchema
from services.airport_service import get_airport_by_region_code, get_airports_in_region
from services.configuration_service import (
    get_region_from_location,
    get_state_from_location_v2,
)
from utils.utility import (
    calculate_age_from_dob,
    remove_none_recursive,
    transform_datetime_to_str,
    validate_date_time,
)
from sqlalchemy.orm import Session


def _validate_duplicate_local_bookings(
    booking_request: TripBookRequest,
    requestor: str,
    db: Session,
    overlap_hours: int = 12,
):
    start_date = validate_date_time(date_time=booking_request.preferences.start_date)

    end_date = start_date + timedelta(
        hours=overlap_hours
    )  # Check for bookings within the next 12 hours
    existing_bookings = (
        db.query(Trip)
        .join(TripTypeMaster)
        .filter(
            Trip.trip_type_id == TripTypeMaster.id,
            Trip.creator_id == requestor,
            Trip.start_datetime >= start_date,
            Trip.start_datetime <= end_date,
            Trip.status != TripStatusEnum.cancelled,
        )
        .all()
    )
    if existing_bookings:
        raise CabboException(
            "You already have a booking for this time slot", status_code=400
        )


def _validate_duplicate_outstation_bookings(
    booking_request: TripBookRequest, requestor: str, db: Session
):
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
        raise CabboException(
            "You already have a booking for this time slot", status_code=400
        )


def _validate_airport_bookings(
    booking_request: TripBookRequest,
    requestor: str,
    db: Session,
    overlap_hours: int = 4,
):
    start_date = validate_date_time(date_time=booking_request.preferences.start_date)

    end_date = start_date + timedelta(
        hours=overlap_hours
    )  # Check for bookings within the next 6 hours
    existing_bookings = (
        db.query(Trip)
        .join(TripTypeMaster)
        .filter(
            Trip.trip_type_id == TripTypeMaster.id,
            Trip.creator_id == requestor,
            Trip.start_datetime >= start_date,
            Trip.start_datetime <= end_date,
            Trip.status != TripStatusEnum.cancelled,
        )
        .all()
    )
    if existing_bookings:
        raise CabboException(
            "You already have a booking for this time slot", status_code=400
        )


def _validate_booking_request_hash(
    booking_request: TripBookRequest, requestor: str, db: Session
):
    if not booking_request.option.hash:
        raise CabboException("Booking request must have a unique hash", status_code=400)

    if booking_request.option.hash:
        existing_temp_trip = (
            db.query(TempTrip)
            .filter(
                TempTrip.hash == booking_request.option.hash,
                TempTrip.creator_id == requestor,
            )
            .first()
        )
        if existing_temp_trip:
            trip_schema = TripDetails.model_validate(existing_temp_trip)
            result = trip_schema.model_dump(
                exclude_none=True
            )  # Return the trip schema as a dictionary excluding None values
            trip_details = remove_none_recursive(result)
            trip_details = transform_datetime_to_str(trip_details)
            raise CabboException(
                {
                    "message": "You already have made a similar booking which is incomplete. Please complete the previous booking to continue",
                    "booking_id": existing_temp_trip.id,
                },
                status_code=400,
            )


def validate_booking_request(
    booking_request: TripBookRequest, requestor: str, db: Session
):
    # case 0: Check if the booking request is a valid request with an unique hash
    _validate_booking_request_hash(
        booking_request=booking_request, requestor=requestor, db=db
    )

    # Check conflicting bookings on the same time range for the same customer based on trip type

    # case 1: If the trip is local, check for existing bookings for the same customer with the same start date within the next 24 hours

    if booking_request.preferences.trip_type == TripTypeEnum.local:
        _validate_duplicate_local_bookings(
            booking_request=booking_request, requestor=requestor, db=db
        )

    # case 2: If the trip is outstation, check for existing bookings for the same customer between the start and end dates

    elif booking_request.preferences.trip_type == TripTypeEnum.outstation:
        _validate_duplicate_outstation_bookings(
            booking_request=booking_request, requestor=requestor, db=db
        )

    # case 3: If the trip is airport pickup or drop, check for existing bookings for the same customer with the same start date within the next 6 hours
    elif booking_request.preferences.trip_type in [
        TripTypeEnum.airport_pickup,
        TripTypeEnum.airport_drop,
    ]:
        _validate_airport_bookings(
            booking_request=booking_request, requestor=requestor, db=db
        )

    else:
        raise CabboException(
            f"Trip type {booking_request.preferences.trip_type} is not supported for booking",
            status_code=501,
        )


def validate_serviceable_area(
    search_in: TripSearchRequest, config_store: ConfigStore, db: Session
):
    """
    Validates if the trip search request is within the serviceable area for the given trip type.
    Raises CabboException if the request is outside the serviceable area.
    """

    trip_type = search_in.trip_type
    pickup = search_in.origin
    drop = search_in.destination

    # Airport trips and local trips
    if trip_type in [
        TripTypeEnum.airport_pickup,
        TripTypeEnum.airport_drop,
        TripTypeEnum.local,
    ]:
        if trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
            if (
                not config_store.airport_locations
                or len(config_store.airport_locations) == 0
            ):
                raise CabboException(
                    "No airport locations are configured in the system, Airport trips cannot be processed",
                    status_code=500,
                )
        # Region specific trip types
        if trip_type == TripTypeEnum.airport_pickup:
            if not drop:
                raise CabboException(
                    "Destination location is required for airport pickup",
                    status_code=400,
                )
            dest_region = get_region_from_location(
                location=drop, config_store=config_store
            )
            

            if not dest_region:
                raise CabboException(
                    "Destination region is not serviceable", status_code=400
                )
            
            drop.region = dest_region.region_name
            drop.region_code = dest_region.region_code
            drop.state= dest_region.state_name
            drop.state_code= dest_region.state_code
            drop.country_code= dest_region.country_code
            drop.country= dest_region.country_name
            
            if not pickup:
                dest_region_airport_locations = (
                    dest_region.airport_locations or []
                )  # list of JSON Ids from master airports in this region

                if (
                    not dest_region_airport_locations
                    or len(dest_region_airport_locations) == 0
                ):
                    raise CabboException("No airports found in region", status_code=400)

                # Accumulate the AirportSchema objects from the config_store.airport_locations based on the Ids in dest_region_airport_locations
                airports_in_dest_region: List[AirportSchema] = get_airports_in_region(
                    dest_region_airport_locations, config_store
                )

                if not airports_in_dest_region or len(airports_in_dest_region) == 0:
                    raise CabboException("No airports found in region", status_code=400)

                airport_in_dest_region = get_airport_by_region_code(
                    region_code=dest_region.region_code,
                    airports=airports_in_dest_region,
                )

                if not airport_in_dest_region:
                    raise CabboException("No airport found in region", status_code=400)

                pickup = LocationInfo.model_validate(
                    json.loads(airport_in_dest_region.model_dump_json(exclude_none=True))
                )
                search_in.origin = pickup
            else:
                # Validate that we support this pickup location and it is an airport
                origin_region = get_region_from_location(
                    location=pickup, config_store=config_store
                )
                if not origin_region:
                    raise CabboException(
                        "Origin region is not serviceable", status_code=400
                    )
                airport_locations = (
                    origin_region.airport_locations or []
                )  # List of JSON Ids from master airports in this region

                if not airport_locations or len(airport_locations) == 0:
                    raise CabboException("No airports found in region", status_code=400)

                airports_in_origin_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )

                if not airports_in_origin_region or len(airports_in_origin_region) == 0:
                    raise CabboException("No airports found in region", status_code=400)

                # Check if atleast one airport in the origin region matches the pickup location
                airport_codes = [
                    LocationInfo.model_validate(json.loads(loc)).place_id
                    for loc in airports_in_origin_region
                ]
                if pickup.place_id not in airport_codes:
                    raise CabboException(
                        "Origin location is not a valid airport in the region",
                        status_code=400,
                    )
                pickup.region = origin_region.region_name
                pickup.region_code = origin_region.region_code
                pickup.state= origin_region.state_name
                pickup.state_code= origin_region.state_code
                pickup.country_code= origin_region.country_code
                pickup.country= origin_region.country_name

        elif trip_type == TripTypeEnum.airport_drop:
            if not pickup:
                raise CabboException(
                    "Origin location is required for airport drop", status_code=400
                )
            origin_region = get_region_from_location(
                location=pickup, config_store=config_store
            )
            if not origin_region:
                raise CabboException(
                    "Origin region is not serviceable", status_code=400
                )
            
            pickup.region = origin_region.region_name
            pickup.region_code = origin_region.region_code
            pickup.state= origin_region.state_name
            pickup.state_code= origin_region.state_code
            pickup.country_code= origin_region.country_code
            pickup.country= origin_region.country_name

            if not drop:
                # Set drop as first airport location of origin region
                airport_locations = (
                    origin_region.airport_locations or []
                )  # List of JSON Ids from master airports in this region
                if not airport_locations:
                    raise CabboException("No airports found in region", status_code=400)

                airports_in_origin_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )
                if not airports_in_origin_region or len(airports_in_origin_region) == 0:
                    raise CabboException("No airports found in region", status_code=400)

                airport_in_origin_region = get_airport_by_region_code(
                    region_code=origin_region.region_code,
                    airports=airports_in_origin_region,
                )
                if not airport_in_origin_region:
                    raise CabboException("No airport found in region", status_code=400)

                drop = LocationInfo.model_validate(
                    json.loads(airport_in_origin_region.model_dump_json())
                )
                search_in.destination = drop
            else:
                # Validate that we support this drop location and it is an airport
                dest_region = get_region_from_location(
                    location=drop, config_store=config_store
                )
                if not dest_region:
                    raise CabboException(
                        "Destination region is not serviceable", status_code=400
                    )

                airport_locations = dest_region.airport_locations or []
                if not airport_locations or len(airport_locations) == 0:
                    raise CabboException("No airports found in region", status_code=400)

                airports_in_dest_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )
                if not airports_in_dest_region or len(airports_in_dest_region) == 0:
                    raise CabboException("No airports found in region", status_code=400)

                # Check if atleast one airport in the dest region matches the drop location
                airport_codes = [
                    LocationInfo.model_validate(json.loads(loc)).place_id
                    for loc in airports_in_dest_region
                ]
                if drop.place_id not in airport_codes:
                    raise CabboException(
                        "Destination location is not a valid airport in the region",
                        status_code=400,
                    )
                drop.region=dest_region.region_name
                drop.region_code = dest_region.region_code
                drop.state= dest_region.state_name
                drop.state_code= dest_region.state_code
                drop.country_code= dest_region.country_code
                drop.country= dest_region.country_name

        elif trip_type == TripTypeEnum.local:
            if not pickup:
                raise CabboException(
                    "Origin location is required for local trip", status_code=400
                )
            origin_region = get_region_from_location(
                location=pickup, config_store=config_store
            )
            if not origin_region:
                raise CabboException(
                    "Origin region is not serviceable", status_code=400
                )
            pickup.region=origin_region.region_name
            pickup.region_code = origin_region.region_code
            pickup.state= origin_region.state_name
            pickup.state_code= origin_region.state_code
            pickup.country_code= origin_region.country_code
            pickup.country= origin_region.country_name
            if not drop:
                drop = pickup  # For local trips, set drop as same as pickup if not provided
                search_in.destination = drop
            else:
                dest_region = get_region_from_location(
                    location=drop, config_store=config_store
                )
                if not dest_region:
                    raise CabboException(
                        "Destination region is not serviceable", status_code=400
                    )
                drop.region=dest_region.region_name
                drop.region_code = dest_region.region_code
                drop.state= dest_region.state_name
                drop.state_code= dest_region.state_code
                drop.country_code= dest_region.country_code
                drop.country= dest_region.country_name
        # Final check: Ensure both pickup and drop are in the same region
        if pickup.region_code != drop.region_code:
            raise CabboException(
                "Both origin and destination must be in the same region",
                status_code=400,
            )

    # Outstation trips
    # For outstation trips, both pickup and drop must be in serviceable states
    elif trip_type == TripTypeEnum.outstation:
        from services.trips.outstation_service import get_allowed_outstation_states

        allowed_states = get_allowed_outstation_states(config_store=config_store)
        if not allowed_states:
            raise CabboException(
                "No states are configured for outstation trips", status_code=500
            )

        if not pickup:
            raise CabboException(
                "Origin location is required for outstation trip", status_code=400
            )
        if not drop:
            raise CabboException(
                "Destination location is required for outstation trip", status_code=400
            )

        origin_state = get_state_from_location_v2(
            location=pickup, config_store=config_store
        )
        if not origin_state:
            raise CabboException("Origin state is not serviceable", status_code=400)

        if origin_state.state_code not in allowed_states:
            raise CabboException(
                f"Outstation trips are only serviceable from: {', '.join(allowed_states)}.",
                status_code=400,
            )
        
        #At this point as we have the state_code, we will enrich origin_state pick up with 
          
        pickup.state= origin_state.state_name
        pickup.country_code= origin_state.country_code
        pickup.country= origin_state.country_name

        dest_state = get_state_from_location_v2(
            location=drop, config_store=config_store
        )
        if not dest_state:
            raise CabboException(
                "Destination state is not serviceable", status_code=400
            )

        if dest_state.state_code not in allowed_states:
            raise CabboException(
                f"Outstation trips are only serviceable to: {', '.join(allowed_states)}.",
                status_code=400,
            )
        
        drop.state= dest_state.state_name
        drop.country_code= dest_state.country_code
        drop.country= dest_state.country_name
        #There is no need of having region or postal code for outstation trips since we are validating at state level and have all state level and higher level info


        if search_in.hops:
            invalid_hops = []
            same_as_drop_hops = []
            zero_coord_hops = []
            duplicate_hops = []
            seen_hop_keys = set()
            unique_hops = []
            
            for hop in search_in.hops:
                hop_state = get_state_from_location_v2(
                    location=hop, config_store=config_store
                )
                # Build a stable key to detect duplicate hops (prefer place_id, fallback to coords)
                if getattr(hop, "place_id", None):
                        hop_key = f"place:{hop.place_id}"
                else:
                        hop_key = f"coord:{hop.lat}:{hop.lng}"
                if hop_key in seen_hop_keys:
                    duplicate_hops.append(hop.state_code)
                    continue  # Skip adding this duplicate hop

                seen_hop_keys.add(hop_key)
                if not hop_state:
                    invalid_hops.append(hop.state_code)
                elif hop_state.state_code not in allowed_states:
                    invalid_hops.append(hop_state.state_code)
                elif hop.lat is None or hop.lng is None:
                    zero_coord_hops.append(hop_state.state_code if hop_state else hop_key)
                elif hop.lat == 0.0 or hop.lng == 0.0:
                    zero_coord_hops.append(hop_state.state_code if hop_state else hop_key)
                elif (hop.lat == drop.lat and hop.lng == drop.lng) or (
                        getattr(hop, "place_id", None) and hop.place_id == drop.place_id
                    ): # Same as drop, do not consider and si
                    same_as_drop_hops.append(hop_state.state_code if hop_state else hop_key)
                    continue  # Skip adding this hop
                
                if hop_state and hop_state.state_code not in same_as_drop_hops:
                    hop.state= hop_state.state_name
                    hop.country_code= hop_state.country_code
                    hop.country= hop_state.country_name
                unique_hops.append(hop)
            
            if duplicate_hops:
                    print(
                        f"Note: Duplicate hops detected and ignored: {len(duplicate_hops)}"
                    )
            if same_as_drop_hops:
                    print(
                        f"Note: The following hops are same as destination and will be ignored: {', '.join(same_as_drop_hops)}"
                    )
            if zero_coord_hops:
                    print(
                        f"Note: The following hops have zero or missing coordinates and will be ignored: {', '.join(zero_coord_hops)}"
                    )
            # Keep only unique, valid hops (invalid hops cause an exception below)
            search_in.hops = [
                    h
                    for h in unique_hops
                    if (getattr(h, "state_code", None) not in zero_coord_hops)
                ]
            if invalid_hops:
                message = f"Outstation trips are only serviceable to: {', '.join(allowed_states)}."
                # Convert None to 'Unknown' or just str
                context = (
                    "One or more hops in your trip is not serviceable: "
                    f"{', '.join([str(h) if h is not None else 'Unknown' for h in invalid_hops])}, "
                    "try again with different hops within serviceable states or remove them."
                )
                #Only raise exception if there are invalid hops
                raise CabboException(
                    {
                        "message": message,
                        "context": context,
                    },
                    status_code=400,
                )
            

    else:
        raise CabboException(f"Trip type {trip_type} is not supported", status_code=501)
    print("Serviceable area validation passed")
    return search_in


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


def validate_trip_type(trip_type: TripTypeEnum, config_store: ConfigStore):
    """
    Validates if the provided trip type is supported.

    Args:
        trip_type (TripTypeEnum): The trip type to validate.
        config_store (ConfigStore): The configuration store instance.
    Raises:
        CabboException: If the trip type is not supported.
    """
    supported_trip_types = {t.trip_type for t in config_store.trip_types}
    if trip_type not in supported_trip_types:
        raise CabboException(
            f"Trip type {trip_type.value} is not supported", status_code=501
        )


def validate_phone_by_country(phone: str, country: CountrySchema) -> str:
    """
    Validate and sanitize phone number based on country configuration.

    Args:
        phone: Phone number to validate
        country: Country configuration from ConfigStore

    Returns:
        Sanitized phone number with country code
    """
    # Remove spaces, hyphens, parentheses
    phone = re.sub(r"[\s\-\(\)]", "", phone)

    # Extract number without country code
    if phone.startswith(country.phone_code):
        num = phone[len(country.phone_code) :]
    elif phone.startswith("+"):
        # Remove any country code
        num = re.sub(r"^\+\d+", "", phone)
    else:
        num = phone

    # Validate length
    if len(num) < country.phone_min_length or len(num) > country.phone_max_length:
        example = country.phone_example if country.phone_example else f"+<country code>{'X'*country.phone_min_length}"
        
        raise CabboException(
            f"Invalid phone number. Expected {country.phone_min_length} digits. Example: {example}",
            status_code=422,
        )

    # Validate regex
    if not re.fullmatch(country.phone_regex, num):
        example = country.phone_example if country.phone_example else f"+<country code>{'X'*country.phone_min_length}"
      
        raise CabboException(
            f"Invalid phone number format for {country.name}. Example: {example}",
            status_code=422,
        )

    return country.phone_code+" "+num


def validate_postal_code_by_country(postal_code: str, country: CountrySchema) -> str:
    """Validate postal code based on country configuration."""
    postal_code = postal_code.strip().upper()

    if not re.fullmatch(country.postal_code_regex, postal_code):
        raise CabboException(
            f"Invalid postal code format for {country.name}", status_code=422
        )

    return postal_code


def validate_driver_age_by_country(age: int, country: CountrySchema):
    """Validate driver age based on country rules."""
    if age < country.min_age_for_drivers or age > country.max_age_for_drivers:
        raise CabboException(
            f"Minimum age for driver in {country.country_name} is {country.min_age_for_drivers} and maximum age is {country.max_age_for_drivers}",
            status_code=422,
        )
    return True


def validate_customer_age_by_country(age: int, country: CountrySchema):
    """Validate customer age based on country rules."""
    if age < country.min_age_for_customers or age > country.max_age_for_customers:
        raise CabboException(
            f"Minimum age for customer in {country.country_name} is {country.min_age_for_customers} and maximum age is {country.max_age_for_customers}",
            status_code=422,
        )


def validate_system_user_age_by_country(age: int, country: CountrySchema):
    """Validate system user age based on country rules."""
    if age < country.min_age_for_system_users or age > country.max_age_for_system_users:
        raise CabboException(
            f"Minimum age for system user in {country.country_name} is {country.min_age_for_system_users} and maximum age is {country.max_age_for_system_users}",
            status_code=422,
        )

def validate_driver_payload(
    payload: Union[DriverUpdateSchema, DriverCreateSchema] = Body(...),
  
):
    db = get_mysql_local_session()
    config_store: ConfigStore = settings.get_config_store(db)
    country = config_store.geographies.country_server
    if not country:
        raise CabboException(
            "Country configuration not found in system", status_code=500
        )
    
    
    
    if isinstance(payload, DriverCreateSchema):
        if not payload.phone or payload.phone.strip() == "":
            raise CabboException(
                "Phone number is required for driver", status_code=400
            )
        
        if not payload.dob:
            raise CabboException(
    "Please enter the driver's date of birth so we can check if they meet the minimum age requirement.",
    status_code=400
)
        
    # Validate driver age
    if payload.dob:
        #Get age from dob
        age = calculate_age_from_dob(payload.dob)
        validate_driver_age_by_country(age=age, country=country)
    
    # Validate phone number
    payload.phone = validate_phone_by_country(
        phone=payload.phone, country=country
    )
    # Validate payment phone number
    if payload.payment_phone_number:
        payload.payment_phone_number = validate_phone_by_country(
            phone=payload.payment_phone_number, country=country
        )
    if not payload.payment_phone_number or payload.payment_phone_number.strip() == "":
        payload.payment_phone_number= payload.phone # Use driver's primary phone number if alternate not provided
    
    #Validate emergency contact phone number
    if payload.emergency_contact_number:
        payload.emergency_contact_number = validate_phone_by_country(
            phone=payload.emergency_contact_number, country=country
        )

    return payload

def validate_customer_payload(
    payload: Union[CustomerUpdate, CustomerCreate] = Body(...),
  
):
    db = get_mysql_local_session()
    config_store: ConfigStore = settings.get_config_store(db)
    country = config_store.geographies.country_server
    if not country:
        raise CabboException(
            "Country configuration not found in system", status_code=500
        )
    
    # Validate customer age
    if payload.dob:
        #Get age from dob
        age = calculate_age_from_dob(payload.dob)
        validate_customer_age_by_country(age=age, country=country)
    
    if isinstance(payload, CustomerCreate):
        if not payload.phone_number or payload.phone_number.strip() == "":
            raise CabboException(
                "Phone number is required for customer creation", status_code=400
            )
        # Validate phone number only for creation, we do not allow phone number update
        payload.phone_number = validate_phone_by_country(
            phone=payload.phone_number, country=country
        )
    
    #Validate emergency contact phone number
    if payload.emergency_contact_number and payload.emergency_contact_number.strip() != "":
        payload.emergency_contact_number = validate_phone_by_country(
            phone=payload.emergency_contact_number, country=country
        )

    return payload

def validate_passenger_payload(
    payload: Union[PassengerUpdate, PassengerCreate] = Body(...),
  
):
    db = get_mysql_local_session()
    config_store: ConfigStore = settings.get_config_store(db)
    country = config_store.geographies.country_server
    if not country:
        raise CabboException(
            "Country configuration not found in system", status_code=500
        )
    
    
    
    # Validate phone number
    if payload.phone_number:
        payload.phone_number = validate_phone_by_country(
            phone=payload.phone_number, country=country
        )
    

    return payload

def validate_customer_onboarding_payload(
        payload:CustomerOnboardInitiationRequest = Body(...),
):
    db = get_mysql_local_session()
    config_store: ConfigStore = settings.get_config_store(db)
    country = config_store.geographies.country_server
    if not country:
        raise CabboException(
            "Country configuration not found in system", status_code=500
        )
    
    if not payload.phone_number or payload.phone_number.strip() == "":
        raise CabboException(
            "Phone number is required for customer onboarding", status_code=400
        )
    
    # Validate phone number
    payload.phone_number = validate_phone_by_country(
        phone=payload.phone_number, country=country
    )
    
   

    return payload

def validate_customer_login_payload(
        payload:Union[CustomerLoginRequest, CustomerOnboardInitiationRequest] = Body(...),
):
    db = get_mysql_local_session()
    config_store: ConfigStore = settings.get_config_store(db)
    country = config_store.geographies.country_server
    if not country:
        raise CabboException(
            "Country configuration not found in system", status_code=500
        )
    
    if not payload.phone_number or payload.phone_number.strip() == "":
        raise CabboException(
            "Phone number is required for customer login", status_code=400
        )
    
    # Validate phone number
    payload.phone_number = validate_phone_by_country(
        phone=payload.phone_number, country=country
    )
    
    return payload

def validate_system_user_payload(
    payload: Union[UserCreateSchema, UserUpdateSchema] = Body(...),
  
):
    db = get_mysql_local_session()
    config_store: ConfigStore = settings.get_config_store(db)
    country = config_store.geographies.country_server
    if not country:
        raise CabboException(
            "Country configuration not found in system", status_code=500
        )
    
    # Validate system user age
    if payload.dob:
        #Get age from dob
        age = calculate_age_from_dob(payload.dob)
        validate_system_user_age_by_country(age=age, country=country)
    
    if isinstance(payload, UserCreateSchema):
        if not payload.phone_number or payload.phone_number.strip() == "":
            raise CabboException(
                "Phone number is required for system user creation", status_code=400
            )
        
    # Validate phone number
    if payload.phone_number:
        payload.phone_number = validate_phone_by_country(
            phone=payload.phone_number, country=country
        )
    
    if payload.emergency_contact_number:
        payload.emergency_contact_number = validate_phone_by_country(
            phone=payload.emergency_contact_number, country=country
        )

    return payload