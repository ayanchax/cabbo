from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import List, Union

from fastapi import Body
from core.exceptions import (
    AIRPORT_PICKUP_DESTINATION_REQUIRED,
    AIRPORT_TRIP_START_DATE_BELOW_PRIOR_BOOKING_WINDOW,
    AIRPORT_TRIP_START_DATE_IN_PAST,
    ALREADY_BOOKED_ON_THIS_SLOT,
    DESTINATION_LOCATION_NOT_VALID_AIRPORT,
    DESTINATION_REGION_NOT_SERVICEABLE,
    DESTINATION_STATE_NOT_SERVICEABLE,
    DISTANCE_ABOVE_MAXIMUM_THRESHOLD,
    DISTANCE_BELOW_MINIMUM_THRESHOLD,
    DISTANCE_NOT_DETERMINED,
    DISTANCE_ZERO_OR_NEGATIVE,
    GENERIC_EXCEPTION,
    LOCAL_TRIP_ORIGIN_REQUIRED,
    LOCAL_TRIP_START_DATE_BELOW_PRIOR_BOOKING_WINDOW,
    LOCAL_TRIP_START_DATE_IN_PAST,
    NO_AIRPORTS_CONFIGURED,
    NO_AIRPORTS_IN_DESTINATION_REGION,
    NO_AIRPORTS_IN_ORIGIN_REGION,
    NO_LOCAL_TRIP_PACKAGES_IN_ORIGIN_REGION,
    ORIGIN_DESTINATION_REGION_MISMATCH,
    ORIGIN_LOCATION_NOT_VALID_AIRPORT,
    ORIGIN_REGION_NOT_CONFIGURED,
    ORIGIN_REGION_NOT_DETERMINED,
    ORIGIN_REGION_NOT_SERVICEABLE,
    ORIGIN_STATE_NOT_SERVICEABLE,
    OUTSTATION_CONSECUTIVE_HOPS_ZERO_DISTANCE,
    OUTSTATION_DATES_IN_PAST,
    OUTSTATION_HOP_NOT_SERVICEABLE,
    OUTSTATION_HOPS_EXCEEDS_MAX_LIMIT,
    OUTSTATION_START_DATE_AFTER_END_DATE,
    OUTSTATION_START_DATE_BELOW_PRIOR_BOOKING_WINDOW,
    OUTSTATION_TOTAL_DAYS_ABOVE_MAXIMUM_THRESHOLD,
    OUTSTATION_TOTAL_DAYS_BELOW_MINIMUM_THRESHOLD,
    OUTSTATION_TRIP_DESTINATION_NOT_ALLOWED,
    OUTSTATION_TRIP_DESTINATION_REQUIRED,
    OUTSTATION_TRIP_ORIGIN_NOT_ALLOWED,
    OUTSTATION_TRIP_ORIGIN_REQUIRED,
    OUTSTATION_TRIP_SCHEDULE_REQUIRED,
    TRIP_TYPE_NOT_CONFIGURED,
    TRIP_TYPE_NOT_SUPPORTED,
    AIRPORT_TRIP_START_DATE_REQUIRED,
    LOCAL_TRIP_START_DATE_REQUIRED,
    CabboException,
)
from core.config import settings

# from models.geography.service_area_orm import ServiceableGeographyOrm
from core.store import ConfigStore
from core.trip_constants import DEFAULT_PRIOR_BOOKING_WINDOW_HOURS, OUTSTATION_DEFAULTS
from core.trip_helpers import get_prior_booking_window_hours
from db.database import get_mysql_local_session
from models.airport.airport_schema import AirportSchema
from models.customer.customer_schema import (
    CustomerCreate,
    CustomerLoginRequest,
    CustomerOTPRequest,
    CustomerOnboardInitiationRequest,
    CustomerUpdate,
)
from models.customer.passenger_schema import PassengerCreate, PassengerUpdate
from models.driver.driver_schema import DriverCreateSchema, DriverUpdateSchema
from models.geography.country_schema import CountrySchema
from models.geography.state_schema import StateSchema
from models.map.location_schema import LocationInfo
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
from models.trip.trip_orm import Trip, TripTypeMaster
from models.trip.trip_schema import (
    TripBookRequest,
    TripClassificationRequest,
    TripSearchRequest,
)
from models.user.user_schema import UserCreateSchema, UserUpdateSchema
from services.airport_service import (
    get_airport_by_region_code,
    get_airports_in_region,
    match_location_to_airport,
)
from services.configuration_service import (
    get_region_from_location,
    get_state_from_location_v2,
)
from services.location_service import get_distance_km, get_distance_km_haversine
from utils.utility import (
    calculate_age_from_dob,
    validate_date_time,
)
from sqlalchemy.orm import Session
import logging

log = logging.getLogger(__name__)


def _validate_duplicate_local_bookings(
    booking_request: TripBookRequest,
    requestor: str,
    db: Session,
    overlap_hours: int = 12,
):
    start_date = validate_date_time(date_time=booking_request.preferences.start_date, timezone_str=booking_request.metadata.timezone)

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
            "You already have a booking for this time slot",
            status_code=400,
            error_code=ALREADY_BOOKED_ON_THIS_SLOT,
        )


def _validate_duplicate_outstation_bookings(
    booking_request: TripBookRequest, requestor: str, db: Session
):
    timezone = booking_request.metadata.timezone if booking_request.metadata and booking_request.metadata.timezone else settings.CABBO_DEFAULT_TIMEZONE
    start_date = validate_date_time(date_time=booking_request.preferences.start_date, timezone_str=timezone)

    end_date = validate_date_time(date_time=booking_request.preferences.end_date, timezone_str=timezone)

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
            "You already have a booking for this time slot",
            status_code=400,
            error_code=ALREADY_BOOKED_ON_THIS_SLOT,
        )


def _validate_airport_bookings(
    booking_request: TripBookRequest,
    requestor: str,
    db: Session,
    overlap_hours: int = 4,
):
    timezone = booking_request.metadata.timezone if booking_request.metadata and booking_request.metadata.timezone else settings.CABBO_DEFAULT_TIMEZONE
    start_date = validate_date_time(date_time=booking_request.preferences.start_date, timezone_str=timezone)

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
            "You already have a booking for this time slot",
            status_code=400,
            error_code=ALREADY_BOOKED_ON_THIS_SLOT,
        )


def _validate_booking_request_hash(
    booking_request: TripBookRequest, requestor: str, db: Session, allow_removal_of_existing: bool = False
):
    if not booking_request.option.hash:
        raise CabboException(
            "Booking request must have a unique hash",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )

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
            # Ensure both datetimes are timezone-aware (UTC)
            created_at = existing_temp_trip.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            

            if created_at < datetime.now(timezone.utc) - timedelta(minutes=29):
                # If the temp trip is older than 29 minutes, we consider it expired and remove it to allow fresh booking attempts, since Razorpay orders typically expire after 30 minutes, so a temp trip older than 29 minutes is unlikely to be valid.
                db.delete(existing_temp_trip)
                db.commit()
                return None, None

            # Check if the existing temp trip has payment provider metadata and a valid Razorpay order id, if not, we consider it invalid and remove it to allow fresh booking attempts, since without a valid Razorpay order id, there is no way to validate the temp trip and it could be a stale entry from an abandoned booking attempt. This is an important check to prevent blocking users from making new booking attempts due to stale temp trip entries that do not have valid payment provider metadata and order ids, which can happen if there were issues during temp trip creation or if the user abandoned the booking process before completing payment.
            ppm = existing_temp_trip.payment_provider_metadata
            order_id = None
            if ppm:
                key = f"{settings.PAYMENT_PROVIDER}_order_id"
                order_id = ppm.get(key) if isinstance(ppm, dict) else getattr(ppm, key, None)
            if not order_id:
                # If there is no payment provider metadata or order id, we consider this temp trip as invalid and remove it to allow fresh booking attempts, since without payment provider metadata and order id, there is no way to validate the temp trip and it could be a stale entry from an abandoned booking attempt.
                db.delete(existing_temp_trip)
                db.commit()
                return None, None

            

            
            if allow_removal_of_existing:
                db.delete(existing_temp_trip)
                db.commit()
                return None, None

            return existing_temp_trip, order_id
        return None, None


def validate_booking_request(
    booking_request: TripBookRequest, requestor: str, db: Session
):
    # case 0: Check if the booking request is a valid request with an unique hash
    existing_trip_details, order_id = _validate_booking_request_hash(
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
            error_code=TRIP_TYPE_NOT_SUPPORTED,
        )
    return existing_trip_details, order_id

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
                    error_code=NO_AIRPORTS_CONFIGURED,
                )
        # Region specific trip types
        if trip_type == TripTypeEnum.airport_pickup:
            if not drop:
                raise CabboException(
                    "Destination location is required for airport pickup",
                    status_code=400,
                    error_code=AIRPORT_PICKUP_DESTINATION_REQUIRED,
                )
            dest_region = get_region_from_location(
                location=drop, config_store=config_store
            )

            if not dest_region:
                raise CabboException(
                    "Destination region is not serviceable",
                    status_code=400,
                    error_code=DESTINATION_REGION_NOT_SERVICEABLE,
                )

            drop.region = dest_region.region_name
            drop.region_code = dest_region.region_code
            drop.state = dest_region.state_name
            drop.state_code = dest_region.state_code
            drop.country_code = dest_region.country_code
            drop.country = dest_region.country_name

            if not pickup:
                dest_region_airport_locations = (
                    dest_region.airport_locations or []
                )  # list of JSON Ids from master airports in this region

                if (
                    not dest_region_airport_locations
                    or len(dest_region_airport_locations) == 0
                ):
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                # Accumulate the AirportSchema objects from the config_store.airport_locations based on the Ids in dest_region_airport_locations
                airports_in_dest_region: List[AirportSchema] = get_airports_in_region(
                    dest_region_airport_locations, config_store
                )

                if not airports_in_dest_region or len(airports_in_dest_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                airport_in_dest_region = get_airport_by_region_code(
                    region_code=dest_region.region_code,
                    airports=airports_in_dest_region,
                )

                if not airport_in_dest_region:
                    raise CabboException(
                        "No airport found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                pickup = LocationInfo.model_validate(
                    json.loads(
                        airport_in_dest_region.model_dump_json(exclude_none=True)
                    )
                )
                search_in.origin = pickup
            else:
                # Validate that we support this pickup location and it is an airport
                origin_region = get_region_from_location(
                    location=pickup, config_store=config_store
                )
                if not origin_region:
                    raise CabboException(
                        "Origin region is not serviceable",
                        status_code=400,
                        error_code=ORIGIN_REGION_NOT_SERVICEABLE,
                    )
                airport_locations = (
                    origin_region.airport_locations or []
                )  # List of JSON Ids from master airports in this region

                if not airport_locations or len(airport_locations) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                airports_in_origin_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )

                if not airports_in_origin_region or len(airports_in_origin_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                # Check if the pickup location matches at least one known airport in the region
                if not match_location_to_airport(pickup, airports_in_origin_region):
                    raise CabboException(
                        "Origin location is not a valid airport in the region",
                        status_code=400,
                        error_code=ORIGIN_LOCATION_NOT_VALID_AIRPORT,
                    )
                pickup.region = origin_region.region_name
                pickup.region_code = origin_region.region_code
                pickup.state = origin_region.state_name
                pickup.state_code = origin_region.state_code
                pickup.country_code = origin_region.country_code
                pickup.country = origin_region.country_name

        elif trip_type == TripTypeEnum.airport_drop:
            if not pickup:
                raise CabboException(
                    "Origin location is required for airport drop",
                    status_code=400,
                    error_code=ORIGIN_LOCATION_NOT_VALID_AIRPORT,
                )
            origin_region = get_region_from_location(
                location=pickup, config_store=config_store
            )
            if not origin_region:
                raise CabboException(
                    "Origin region is not serviceable",
                    status_code=400,
                    error_code=ORIGIN_REGION_NOT_SERVICEABLE,
                )

            pickup.region = origin_region.region_name
            pickup.region_code = origin_region.region_code
            pickup.state = origin_region.state_name
            pickup.state_code = origin_region.state_code
            pickup.country_code = origin_region.country_code
            pickup.country = origin_region.country_name

            if not drop:
                # Set drop as first airport location of origin region
                airport_locations = (
                    origin_region.airport_locations or []
                )  # List of JSON Ids from master airports in this region
                if not airport_locations:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                airports_in_origin_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )
                if not airports_in_origin_region or len(airports_in_origin_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                airport_in_origin_region = get_airport_by_region_code(
                    region_code=origin_region.region_code,
                    airports=airports_in_origin_region,
                )
                if not airport_in_origin_region:
                    raise CabboException(
                        "No airport found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

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
                        "Destination region is not serviceable",
                        status_code=400,
                        error_code=DESTINATION_REGION_NOT_SERVICEABLE,
                    )

                airport_locations = dest_region.airport_locations or []
                if not airport_locations or len(airport_locations) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                airports_in_dest_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )
                if not airports_in_dest_region or len(airports_in_dest_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                # Check if the drop location matches at least one known airport in the region
                if not match_location_to_airport(drop, airports_in_dest_region):
                    raise CabboException(
                        "Destination location is not a valid airport in the region",
                        status_code=400,
                        error_code=DESTINATION_LOCATION_NOT_VALID_AIRPORT,
                    )
                drop.region = dest_region.region_name
                drop.region_code = dest_region.region_code
                drop.state = dest_region.state_name
                drop.state_code = dest_region.state_code
                drop.country_code = dest_region.country_code
                drop.country = dest_region.country_name

        elif trip_type == TripTypeEnum.local:
            if not pickup:
                raise CabboException(
                    "Origin location is required for local trip",
                    status_code=400,
                    error_code=LOCAL_TRIP_ORIGIN_REQUIRED,
                )
            origin_region = get_region_from_location(
                location=pickup, config_store=config_store
            )
            if not origin_region:
                raise CabboException(
                    "Origin region is not serviceable",
                    status_code=400,
                    error_code=ORIGIN_REGION_NOT_SERVICEABLE,
                )
            # Check if trip package is configured for this region.
            # For local trips, we need to have the trip package configured at region level since we
            # are not allowing cross region local trips and we are validating at region level, so if the region is serviceable, we can be assured that the trip package is also configured for that region. Otherwise, we do not allow local trips if package is not configured at origin region level.
            # This is a critical check to prevent abuse of the local trip type for long distance trips in cases where the pickup location is serviceable but there are no local trip packages configured, which would indicate that local trips are not actually supported in that region.
            trip_packages_by_region = config_store.local.get(origin_region.region_code).auxiliary_pricing.trip_packages or []
            if not trip_packages_by_region or len(trip_packages_by_region) == 0:
                raise CabboException(
                    "No trip packages configured for local trips in the origin region, local trips cannot be processed",
                    status_code=400,
                    error_code=NO_LOCAL_TRIP_PACKAGES_IN_ORIGIN_REGION,
                )
            pickup.region = origin_region.region_name
            pickup.region_code = origin_region.region_code
            pickup.state = origin_region.state_name
            pickup.state_code = origin_region.state_code
            pickup.country_code = origin_region.country_code
            pickup.country = origin_region.country_name
            if not drop:
                drop = pickup  # For local trips, set drop as same as pickup if not provided
                search_in.destination = drop
            else:
                dest_region = get_region_from_location(
                    location=drop, config_store=config_store
                )
                if not dest_region:
                    raise CabboException(
                        "Destination region is not serviceable",
                        status_code=400,
                        error_code=DESTINATION_REGION_NOT_SERVICEABLE,
                    )
                # We do not care about local trip packages in destination region because for local trips, we need to have the trip package configured at origin region level since we are not allowing cross region local trips and we are validating at region level, so if the region is serviceable, we can be assured that the trip package is also configured for that region. Otherwise, we do not allow local trips if package is not configured at origin region level.
                drop.region = dest_region.region_name
                drop.region_code = dest_region.region_code
                drop.state = dest_region.state_name
                drop.state_code = dest_region.state_code
                drop.country_code = dest_region.country_code
                drop.country = dest_region.country_name
        # Final check: Ensure both pickup and drop are in the same region
        if pickup.region_code != drop.region_code:
            raise CabboException(
                "Both origin and destination must be in the same region",
                status_code=400,
                error_code=ORIGIN_DESTINATION_REGION_MISMATCH,
            )

    # Outstation trips
    # For outstation trips, both pickup and drop must be in serviceable states
    elif trip_type == TripTypeEnum.outstation:
        from services.trips.outstation_service import get_allowed_outstation_states

        allowed_states = get_allowed_outstation_states(config_store=config_store)
        if not allowed_states:
            raise CabboException(
                "No states are configured for outstation trips",
                status_code=500,
                error_code=GENERIC_EXCEPTION,
            )

        if not pickup:
            raise CabboException(
                "Origin location is required for outstation trip",
                status_code=400,
                error_code=OUTSTATION_TRIP_ORIGIN_REQUIRED,
            )
        if not drop:
            raise CabboException(
                "Destination location is required for outstation trip",
                status_code=400,
                error_code=OUTSTATION_TRIP_DESTINATION_REQUIRED,
            )

        origin_state = get_state_from_location_v2(
            location=pickup, config_store=config_store
        )
        if not origin_state:
            raise CabboException(
                "Origin state is not serviceable",
                status_code=400,
                error_code=ORIGIN_STATE_NOT_SERVICEABLE,
            )

        if origin_state.state_code not in allowed_states:
            raise CabboException(
                f"Outstation trips are only serviceable from: {', '.join(allowed_states)}.",
                status_code=400,
                error_code=OUTSTATION_TRIP_ORIGIN_NOT_ALLOWED,
            )
        # At this point as we have the state_code, we will enrich origin_state pick up with

        pickup.state = origin_state.state_name
        pickup.country_code = origin_state.country_code
        pickup.country = origin_state.country_name

        dest_state = get_state_from_location_v2(
            location=drop, config_store=config_store
        )
        if not dest_state:
            raise CabboException(
                "Destination state is not serviceable",
                status_code=400,
                error_code=DESTINATION_STATE_NOT_SERVICEABLE,
            )

        if dest_state.state_code not in allowed_states:
            raise CabboException(
                f"Outstation trips are only serviceable to: {', '.join(allowed_states)}.",
                status_code=400,
                error_code=OUTSTATION_TRIP_DESTINATION_NOT_ALLOWED,
            )

        drop.state = dest_state.state_name
        drop.country_code = dest_state.country_code
        drop.country = dest_state.country_name
        # There is no need of having region or postal code for outstation trips since we are validating at state level and have all state level and higher level info
        # Also since outstation trips can happen within same or different region and/or state, there is no need to validate
        # both pickup and drop are in the same region or state.

        if search_in.hops:
            search_in.hops = validate_hops(
                hops=search_in.hops,
                config_store=config_store,
                dest_state=dest_state,
                allowed_states=allowed_states,
                drop=drop,
            )

    else:
        raise CabboException(
            f"Trip type {trip_type} is not supported",
            status_code=501,
            error_code=TRIP_TYPE_NOT_SUPPORTED,
        )

    validate_distance_and_time_constraints(
        pickup=pickup,
        drop=drop,
        config_store=config_store,
        trip_type=trip_type,
        start_date=search_in.start_date,
        end_date=search_in.end_date,
    )
    log.info("Serviceable area validation passed")
    return search_in


def validate_initial_serviceable_area(
    classification_request: TripClassificationRequest, config_store: ConfigStore
):
    """
    Validates if the initial classification request is within the serviceable area for the given trip type.
    Raises CabboException if the request is outside the serviceable area.
    """

    trip_type = classification_request.trip_type
    pickup = classification_request.pickup
    drop = classification_request.dropoff

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
                    error_code=NO_AIRPORTS_CONFIGURED,
                )
        # Region specific trip types
        if trip_type == TripTypeEnum.airport_pickup:
            if not drop:
                raise CabboException(
                    "Destination location is required for airport pickup",
                    status_code=400,
                    error_code=AIRPORT_PICKUP_DESTINATION_REQUIRED,
                )
            dest_region = get_region_from_location(
                location=drop, config_store=config_store
            )

            if not dest_region:
                raise CabboException(
                    "Destination region is not serviceable",
                    status_code=400,
                    error_code=DESTINATION_REGION_NOT_SERVICEABLE,
                )

            drop.region = dest_region.region_name
            drop.region_code = dest_region.region_code
            drop.state = dest_region.state_name
            drop.state_code = dest_region.state_code
            drop.country_code = dest_region.country_code
            drop.country = dest_region.country_name

            if not pickup:
                dest_region_airport_locations = (
                    dest_region.airport_locations or []
                )  # list of JSON Ids from master airports in this region

                if (
                    not dest_region_airport_locations
                    or len(dest_region_airport_locations) == 0
                ):
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                # Accumulate the AirportSchema objects from the config_store.airport_locations based on the Ids in dest_region_airport_locations
                airports_in_dest_region: List[AirportSchema] = get_airports_in_region(
                    dest_region_airport_locations, config_store
                )

                if not airports_in_dest_region or len(airports_in_dest_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                airport_in_dest_region = get_airport_by_region_code(
                    region_code=dest_region.region_code,
                    airports=airports_in_dest_region,
                )

                if not airport_in_dest_region:
                    raise CabboException(
                        "No airport found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                pickup = LocationInfo.model_validate(
                    json.loads(
                        airport_in_dest_region.model_dump_json(exclude_none=True)
                    )
                )
                classification_request.pickup = pickup
            else:
                # Validate that we support this pickup location and it is an airport
                origin_region = get_region_from_location(
                    location=pickup, config_store=config_store
                )
                if not origin_region:
                    raise CabboException(
                        "Origin region is not serviceable",
                        status_code=400,
                        error_code=ORIGIN_REGION_NOT_SERVICEABLE,
                    )
                airport_locations = (
                    origin_region.airport_locations or []
                )  # List of JSON Ids from master airports in this region

                if not airport_locations or len(airport_locations) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                airports_in_origin_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )

                if not airports_in_origin_region or len(airports_in_origin_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                # Check if the pickup location matches at least one known airport in the region
                if not match_location_to_airport(pickup, airports_in_origin_region):
                    raise CabboException(
                        "Origin location is not a valid airport in the region",
                        status_code=400,
                        error_code=ORIGIN_LOCATION_NOT_VALID_AIRPORT,
                    )
                pickup.region = origin_region.region_name
                pickup.region_code = origin_region.region_code
                pickup.state = origin_region.state_name
                pickup.state_code = origin_region.state_code
                pickup.country_code = origin_region.country_code
                pickup.country = origin_region.country_name

        elif trip_type == TripTypeEnum.airport_drop:
            if not pickup:
                raise CabboException(
                    "Origin location is required for airport drop",
                    status_code=400,
                    error_code=AIRPORT_PICKUP_DESTINATION_REQUIRED,
                )
            origin_region = get_region_from_location(
                location=pickup, config_store=config_store
            )
            if not origin_region:
                raise CabboException(
                    "Origin region is not serviceable",
                    status_code=400,
                    error_code=ORIGIN_REGION_NOT_SERVICEABLE,
                )

            pickup.region = origin_region.region_name
            pickup.region_code = origin_region.region_code
            pickup.state = origin_region.state_name
            pickup.state_code = origin_region.state_code
            pickup.country_code = origin_region.country_code
            pickup.country = origin_region.country_name

            if not drop:
                # Set drop as first airport location of origin region
                airport_locations = (
                    origin_region.airport_locations or []
                )  # List of JSON Ids from master airports in this region
                if not airport_locations:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                airports_in_origin_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )
                if not airports_in_origin_region or len(airports_in_origin_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                airport_in_origin_region = get_airport_by_region_code(
                    region_code=origin_region.region_code,
                    airports=airports_in_origin_region,
                )
                if not airport_in_origin_region:
                    raise CabboException(
                        "No airport found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_ORIGIN_REGION,
                    )

                drop = LocationInfo.model_validate(
                    json.loads(airport_in_origin_region.model_dump_json())
                )
                classification_request.dropoff = drop
            else:
                # Validate that we support this drop location and it is an airport
                dest_region = get_region_from_location(
                    location=drop, config_store=config_store
                )
                if not dest_region:
                    raise CabboException(
                        "Destination region is not serviceable",
                        status_code=400,
                        error_code=DESTINATION_REGION_NOT_SERVICEABLE,
                    )

                airport_locations = dest_region.airport_locations or []
                if not airport_locations or len(airport_locations) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                airports_in_dest_region: List[AirportSchema] = get_airports_in_region(
                    airport_locations, config_store
                )
                if not airports_in_dest_region or len(airports_in_dest_region) == 0:
                    raise CabboException(
                        "No airports found in region",
                        status_code=400,
                        error_code=NO_AIRPORTS_IN_DESTINATION_REGION,
                    )

                # Check if the drop location matches at least one known airport in the region
                if not match_location_to_airport(drop, airports_in_dest_region):
                    raise CabboException(
                        "Destination location is not a valid airport in the region",
                        status_code=400,
                        error_code=DESTINATION_LOCATION_NOT_VALID_AIRPORT,
                    )
                drop.region = dest_region.region_name
                drop.region_code = dest_region.region_code
                drop.state = dest_region.state_name
                drop.state_code = dest_region.state_code
                drop.country_code = dest_region.country_code
                drop.country = dest_region.country_name

        elif trip_type == TripTypeEnum.local:
            if not pickup:
                raise CabboException(
                    "Origin location is required for local trip",
                    status_code=400,
                    error_code=LOCAL_TRIP_ORIGIN_REQUIRED,
                )
            origin_region = get_region_from_location(
                location=pickup, config_store=config_store
            )
            if not origin_region:
                raise CabboException(
                    "Origin region is not serviceable",
                    status_code=400,
                    error_code=ORIGIN_REGION_NOT_SERVICEABLE,
                )
            # Check if trip package is configured for this region.
            # For local trips, we need to have the trip package configured at region level since we are not allowing cross region local trips and we are validating at region level, so if the region is serviceable, we can be assured that the trip package is also configured for that region.
            # otherwise, we do not allow local trips if package is not configured at origin region level.
            trip_packages_by_region = config_store.local.get(origin_region.region_code).auxiliary_pricing.trip_packages or []
            if not trip_packages_by_region or len(trip_packages_by_region) == 0:
                raise CabboException(
                    "No trip packages configured for local trips in the origin region, local trips cannot be processed",
                    status_code=400,
                    error_code=NO_LOCAL_TRIP_PACKAGES_IN_ORIGIN_REGION,
                )
            pickup.region = origin_region.region_name
            pickup.region_code = origin_region.region_code
            pickup.state = origin_region.state_name
            pickup.state_code = origin_region.state_code
            pickup.country_code = origin_region.country_code
            pickup.country = origin_region.country_name
            if not drop:
                drop = pickup  # For local trips, set drop as same as pickup if not provided
                if classification_request.swap_empty_with_non_empty:
                    classification_request.dropoff = drop
            else:
                dest_region = get_region_from_location(
                    location=drop, config_store=config_store
                )
                if not dest_region:
                    raise CabboException(
                        "Destination region is not serviceable",
                        status_code=400,
                        error_code=DESTINATION_REGION_NOT_SERVICEABLE,
                    )
                #We do not care about local trip packages in destination region because for local trips, we need to have the trip package configured at origin region level since we are not allowing cross region local trips and we are validating at region level, so if the region is serviceable, we can be assured that the trip package is also configured for that region. Otherwise, we do not allow local trips if package is not configured at origin region level.
                drop.region = dest_region.region_name
                drop.region_code = dest_region.region_code
                drop.state = dest_region.state_name
                drop.state_code = dest_region.state_code
                drop.country_code = dest_region.country_code
                drop.country = dest_region.country_name
        # Final check: Ensure both pickup and drop are in the same region
        if pickup.region_code != drop.region_code:
            raise CabboException(
                "Both origin and destination must be in the same region",
                status_code=400,
                error_code=ORIGIN_DESTINATION_REGION_MISMATCH,
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
                "Origin location is required for outstation trip",
                status_code=400,
                error_code=OUTSTATION_TRIP_ORIGIN_REQUIRED,
            )
        if not drop:
            raise CabboException(
                "Destination location is required for outstation trip",
                status_code=400,
                error_code=OUTSTATION_TRIP_DESTINATION_REQUIRED,
            )

        origin_state = get_state_from_location_v2(
            location=pickup, config_store=config_store
        )
        if not origin_state:
            raise CabboException(
                "Origin state is not serviceable",
                status_code=400,
                error_code=ORIGIN_STATE_NOT_SERVICEABLE,
            )

        if origin_state.state_code not in allowed_states:
            raise CabboException(
                f"Outstation trips are only serviceable from: {', '.join(allowed_states)}.",
                status_code=400,
                error_code=OUTSTATION_TRIP_ORIGIN_NOT_ALLOWED,
            )
        # At this point as we have the state_code, we will enrich origin_state pick up with

        pickup.state = origin_state.state_name
        pickup.country_code = origin_state.country_code
        pickup.country = origin_state.country_name

        dest_state = get_state_from_location_v2(
            location=drop, config_store=config_store
        )
        if not dest_state:
            raise CabboException(
                "Destination state is not serviceable",
                status_code=400,
                error_code=DESTINATION_STATE_NOT_SERVICEABLE,
            )

        if dest_state.state_code not in allowed_states:
            raise CabboException(
                f"Outstation trips are only serviceable to: {', '.join(allowed_states)}.",
                status_code=400,
                error_code=OUTSTATION_TRIP_DESTINATION_NOT_ALLOWED,
            )

        drop.state = dest_state.state_name
        drop.country_code = dest_state.country_code
        drop.country = dest_state.country_name
        # There is no need of having region or postal code for outstation trips since we are validating at state level and have all state level and higher level info
        # Also since outstation trips can happen within same or different region and/or state, there is no need to validate
        # both pickup and drop are in the same region or state.

    else:
        raise CabboException(
            f"Trip type {trip_type} is not supported",
            status_code=501,
            error_code=TRIP_TYPE_NOT_SUPPORTED,
        )

    log.info("Initial Serviceable area validation passed")
    classification_request.serviceable = True
    return classification_request


def validate_hops(
    hops: List[Union[LocationInfo, str]],
    config_store: ConfigStore,
    dest_state: StateSchema,
    allowed_states: set,
    drop: LocationInfo,
):
    if hops:
        max_allowed_hops = config_store.outstation.get(
            dest_state.state_code
        ).auxiliary_pricing.common.max_hops_allowed

        if len(hops) > max_allowed_hops:
            raise CabboException(
                f"Number of hops/stops in outstation trip cannot exceed {max_allowed_hops}, please reduce the number of hops and try again",
                status_code=400,
                error_code=OUTSTATION_HOPS_EXCEEDS_MAX_LIMIT,
            )
        invalid_hops = []
        same_as_drop_hops = []
        zero_coord_hops = []
        duplicate_hops = []
        seen_hop_keys = set()
        unique_hops = []

        for hop in hops:
            hop_state = get_state_from_location_v2(
                location=hop, config_store=config_store
            )
            # Build a stable key to detect duplicate hops (prefer place_id, fallback to coords)
            if getattr(hop, "place_id", None):
                hop_key = f"place:{hop.place_id}"
            else:
                hop_key = f"coord:{hop.lat}:{hop.lng}"
            if hop_key in seen_hop_keys:
                duplicate_hops.append(hop.state_code if hop_state else hop_key)
                continue  # Skip adding this duplicate hop

            seen_hop_keys.add(hop_key)
            if not hop_state:
                invalid_hops.append(hop.state_code if hop_state else hop_key)
                continue
            elif hop_state.state_code not in allowed_states:
                invalid_hops.append(hop_state.state_code if hop_state else hop_key)
                continue
            elif hop.lat is None or hop.lng is None:
                zero_coord_hops.append(
                    hop_key
                )  # For missing coordinates, we don't have state info, so we just use the coordinate key for messaging
                continue

            elif hop.lat == 0.0 or hop.lng == 0.0:
                zero_coord_hops.append(
                    hop_key
                )  # For zero coordinates, we don't have state info, so we just use the coordinate key for messaging
                continue
            elif (hop.lat == drop.lat and hop.lng == drop.lng) or (
                getattr(hop, "place_id", None) and hop.place_id == drop.place_id
            ):  # Same as drop, do not consider as invalid but ignore and do not add to hops, also add to same_as_drop_hops for messaging
                same_as_drop_hops.append(hop.state_code if hop_state else hop_key)
                continue  # Skip adding this hop

            if hop_state:
                hop.state = hop_state.state_name
                hop.country_code = hop_state.country_code
                hop.country = hop_state.country_name
            unique_hops.append(hop)

        if duplicate_hops:
            log.info(
                f"Note: Duplicate hops detected and ignored: {len(duplicate_hops)}"
            )
        if same_as_drop_hops:
            log.info(
                f"Note: The following hops are same as destination and will be ignored: {', '.join(same_as_drop_hops)}"
            )
        if zero_coord_hops:
            log.info(
                f"Note: The following hops have zero or missing coordinates and will be ignored: {', '.join(zero_coord_hops)}"
            )

        if invalid_hops:
            # For one or more invalid hops, we will raise an exception with details of which hops are invalid and allowed states for outstation trips. We will convert None values to 'Unknown' in the messaging for better clarity.
            message = f"Outstation trips are only serviceable to: {', '.join(allowed_states)}."
            # Convert None to 'Unknown' or just str
            context = (
                "One or more hops in your trip is not serviceable: "
                f"{', '.join([str(h) if h is not None else 'Unknown' for h in invalid_hops])}, "
                "try again with different hops within serviceable states or remove them."
            )
            # Only raise exception if there are invalid hops
            raise CabboException(
                {
                    "message": message,
                    "context": context,
                },
                status_code=400,
                error_code=OUTSTATION_HOP_NOT_SERVICEABLE,
            )

        # After unique_hops is fully built, do the consecutive zero-distance check

        if len(unique_hops) >= 2:  # We need at least 2 hops to have consecutive hops
            for i in range(len(unique_hops) - 1):
                d = get_distance_km_haversine(
                    origin=unique_hops[i], destination=unique_hops[i + 1]
                )
                if d is not None and d <= 0:
                    raise CabboException(
                        f"Consecutive hops cannot be at the same location: stop {i + 1} and stop {i + 2} are identical",
                        status_code=400,
                        error_code=OUTSTATION_CONSECUTIVE_HOPS_ZERO_DISTANCE,
                    )

        # Keep only unique, valid hops (invalid hops cause an exception below)
        hops = [h for h in unique_hops]

    log.info("Hops validation passed")
    return hops


def validate_distance_and_time_constraints(
    pickup: LocationInfo,
    drop: LocationInfo,
    config_store: ConfigStore,
    trip_type: TripTypeEnum,
    start_date: Union[str, datetime] = None,
    end_date: Union[str, datetime] = None,
    timezone_str: str = None,
):
    try:
        if trip_type == TripTypeEnum.local:
            return 0  # For local trips, we can skip distance validation as it is package based and not distance based
        distance = get_distance_km(origin=pickup, destination=drop)
        if distance is None:
            raise CabboException(
                "Could not calculate distance between origin and destination, please check the locations and try again",
                status_code=400,
                error_code=DISTANCE_NOT_DETERMINED,
            )
        if distance <= 0:
            raise CabboException(
                "Distance between origin and destination cannot be zero or negative, please check the locations and try again",
                status_code=400,
                error_code=DISTANCE_ZERO_OR_NEGATIVE,
            )
        origin_code = (
            pickup.region_code
            if trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]
            else pickup.state_code
        )
        if not origin_code:
            raise CabboException(
                "Could not determine region for origin location, please check the location and try again",
                status_code=400,
                error_code=ORIGIN_REGION_NOT_DETERMINED,
            )
        target_config_dict = {}
        if trip_type == TripTypeEnum.airport_pickup:
            target_config_dict = config_store.airport_pickup
        elif trip_type == TripTypeEnum.airport_drop:
            target_config_dict = config_store.airport_drop
        elif trip_type == TripTypeEnum.outstation:
            target_config_dict = config_store.outstation

        if len(target_config_dict) == 0:
            raise CabboException(
                "No configuration found for trip type, cannot validate distance for airport trips, please contact support",
                status_code=500,
                error_code=TRIP_TYPE_NOT_CONFIGURED,
            )

        if target_config_dict.get(origin_code) is None:
            raise CabboException(
                "No configuration found for origin region, please check the location and try again",
                status_code=400,
                error_code=ORIGIN_REGION_NOT_CONFIGURED,
            )
        min_distance_km = target_config_dict.get(
            origin_code
        ).auxiliary_pricing.common.min_outbound_distance_km

        # Min and max distance constraint validation.
        if min_distance_km and distance < min_distance_km:
            raise CabboException(
                f"Distance between origin and destination is below the minimum threshold of {min_distance_km} km for airport trips in this region, please check the locations and try again",
                status_code=400,
                error_code=DISTANCE_BELOW_MINIMUM_THRESHOLD,
            )
        max_distance_km = target_config_dict.get(
            origin_code
        ).auxiliary_pricing.common.max_distance_km

        if max_distance_km and distance > max_distance_km:
            raise CabboException(
                f"Distance between origin and destination exceeds the maximum threshold of {max_distance_km} km for airport trips in this region, please check the locations and try again",
                status_code=400,
                error_code=DISTANCE_ABOVE_MAXIMUM_THRESHOLD,
            )

        # Time constraints validation for outstation trips
        if trip_type == TripTypeEnum.outstation:
            if start_date is None or end_date is None:
                raise CabboException(
                    "Start date and end date are required for outstation trip",
                    status_code=400,
                )

             
            total_trip_days = _get_total_trip_days(
                start_date=validate_date_time(start_date, timezone_str=timezone_str),
                end_date=validate_date_time(end_date, timezone_str=timezone_str),
            )
            max_allowed_days = target_config_dict.get(
                origin_code
            ).auxiliary_pricing.common.max_days_allowed

            if max_allowed_days and total_trip_days > max_allowed_days:
                raise CabboException(
                    f"Total trip days for outstation trip exceeds the maximum threshold of {max_allowed_days} days for this state, please check the dates and try again",
                    status_code=400,
                    error_code=OUTSTATION_TOTAL_DAYS_ABOVE_MAXIMUM_THRESHOLD,
                )

            min_allowed_days = target_config_dict.get(
                origin_code
            ).auxiliary_pricing.common.min_days_allowed
            if min_allowed_days and total_trip_days < min_allowed_days:
                raise CabboException(
                    f"Total trip days for outstation trip is below the minimum threshold of {min_allowed_days} days for this state, please check the dates and try again",
                    status_code=400,
                    error_code=OUTSTATION_TOTAL_DAYS_BELOW_MINIMUM_THRESHOLD,
                )

        log.info("Distance and time constraints validation passed")
        return distance
    except CabboException as e:
        raise e


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
    - Start date is at least 6 hours from now
    Args:
        search_in (TripSearchRequest): The trip search request containing start date.
    Raises:
        CabboException: If any validation fails, with appropriate error messages.
    """
    if search_in.start_date is None:
        raise CabboException(
            "Start date is required for local trip",
            status_code=400,
            error_code=LOCAL_TRIP_START_DATE_REQUIRED,
        )
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date, timezone_str=search_in.timezone)

    now = datetime.now(timezone.utc)

    # Check for past dates
    if start_date < now:
        raise CabboException(
            "Start date for local trip cannot be in the past.",
            status_code=400,
            error_code=LOCAL_TRIP_START_DATE_IN_PAST,
        )

    region_code = getattr(search_in.origin, "region_code", None)
    prior_booking_window_hours = (
        get_prior_booking_window_hours(
            trip_type=search_in.trip_type, jurisdiction_code=region_code
        )
    ) or DEFAULT_PRIOR_BOOKING_WINDOW_HOURS[
        TripTypeEnum.local
    ]  # Default to 3 hours if not configured

    # Start date must be at least {prior_booking_window_hours} hours after now
    min_start = now + timedelta(hours=prior_booking_window_hours)
    if start_date < min_start:
        raise CabboException(
            f"Start date for local trip must be at least {prior_booking_window_hours} hours from now.",
            status_code=400,
            error_code=LOCAL_TRIP_START_DATE_BELOW_PRIOR_BOOKING_WINDOW,
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
            "Start date and end date are required for outstation trip",
            status_code=400,
            error_code=OUTSTATION_TRIP_SCHEDULE_REQUIRED,
        )
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date, timezone_str=search_in.timezone)

    end_date = validate_date_time(date_time=search_in.end_date, timezone_str=search_in.timezone)

    now = datetime.now(timezone.utc)

    # Check for past dates
    if start_date < now or end_date < now:
        raise CabboException(
            "Start date and end date for outstation trip cannot be in the past.",
            status_code=400,
            error_code=OUTSTATION_DATES_IN_PAST,
        )

    state_code = getattr(search_in.origin, "state_code", None)
    prior_booking_window_hours = (
        get_prior_booking_window_hours(
            trip_type=search_in.trip_type, jurisdiction_code=state_code
        )
    ) or DEFAULT_PRIOR_BOOKING_WINDOW_HOURS[
        TripTypeEnum.outstation
    ]  # Default to 48 hours if not configured
    # Start date must be at least {prior_booking_window_hours} hours after now
    min_start = now + timedelta(hours=prior_booking_window_hours)
    if start_date < min_start:
        raise CabboException(
            f"Start date for outstation trip must be at least {prior_booking_window_hours//24} days from now.",
            status_code=400,
            error_code=OUTSTATION_START_DATE_BELOW_PRIOR_BOOKING_WINDOW,
        )
    if start_date > end_date:
        raise CabboException(
            "Start date cannot be after end date for outstation trip",
            status_code=400,
            error_code=OUTSTATION_START_DATE_AFTER_END_DATE,
        )
    # Calculate total number of trip days (inclusive, ceil if fractional)
    config_store = settings.get_config_store(get_mysql_local_session())
    outstation_config = config_store.outstation.get(state_code, None)  # This is just to check if the state_code is configured for outstation trips, it will raise an exception if not configured
    min_allowed_days = OUTSTATION_DEFAULTS["min_days_allowed"]
    max_allowed_days = OUTSTATION_DEFAULTS["max_days_allowed"]
    if outstation_config:
        min_allowed_days = outstation_config.auxiliary_pricing.common.min_days_allowed or min_allowed_days
        max_allowed_days = outstation_config.auxiliary_pricing.common.max_days_allowed or max_allowed_days

    total_days = _get_total_trip_days(start_date=start_date, end_date=end_date)
    
    if total_days < min_allowed_days:
        raise CabboException(
            f"Total trip days must be at least {min_allowed_days} for outstation trips",
            status_code=400,
            error_code=OUTSTATION_TOTAL_DAYS_BELOW_MINIMUM_THRESHOLD,
        )
    if total_days > max_allowed_days:
        raise CabboException(
            f"Total trip days cannot exceed {max_allowed_days} for outstation trips",
            status_code=400,
            error_code=OUTSTATION_TOTAL_DAYS_ABOVE_MAXIMUM_THRESHOLD,
        )

    return total_days


def validate_airport_schedule(search_in: TripSearchRequest):

    if search_in.start_date is None:
        raise CabboException(
            "Start date is required for airport transfer",
            status_code=400,
            error_code=AIRPORT_TRIP_START_DATE_REQUIRED,
        )
    # Parse and validate start_date
    start_date = validate_date_time(date_time=search_in.start_date, timezone_str=search_in.timezone)

    now = datetime.now(timezone.utc)

    log.info(f"Current time (UTC): {now}")
    log.info(f"Start date (UTC): {start_date}")

    # Check for past dates
    if start_date < now:
        raise CabboException(
            "Start date for airport transfer cannot be in the past.",
            status_code=400,
            error_code=AIRPORT_TRIP_START_DATE_IN_PAST,
        )
    # Start date must be at least {prior_booking_window_hours} hours after now
    region_code = (
        getattr(search_in.origin, "region_code", None)
        if search_in.trip_type == TripTypeEnum.airport_pickup
        else getattr(search_in.destination, "region_code", None)
    )
    prior_booking_window_hours = (
        get_prior_booking_window_hours(
            trip_type=search_in.trip_type, jurisdiction_code=region_code
        )
    ) or DEFAULT_PRIOR_BOOKING_WINDOW_HOURS[
        TripTypeEnum.airport_general
    ]  # Default to 3 hours if not configured
    min_start = now + timedelta(hours=prior_booking_window_hours)

    if start_date < min_start:
        raise CabboException(
            f"Start date for airport trip must be at least {prior_booking_window_hours} hours from now.",
            status_code=400,
            error_code=AIRPORT_TRIP_START_DATE_BELOW_PRIOR_BOOKING_WINDOW,
        )
    search_in.start_date = start_date.strftime("%Y-%m-%dT%H:%M:%SZ") # Format start date with timezone info for consistency, so that client can rely on the format in the response and does not have to do additional parsing to get timezone info if needed, plus can convert to local timezone if needed based on the timezone info in the string
    


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
        example = (
            country.phone_example
            if country.phone_example
            else f"+<country code>{'X'*country.phone_min_length}"
        )

        raise CabboException(
            f"Invalid phone number. Expected {country.phone_min_length} digits. Example: {example}",
            status_code=422,
        )

    # Validate regex
    if not re.fullmatch(country.phone_regex, num):
        example = (
            country.phone_example
            if country.phone_example
            else f"+<country code>{'X'*country.phone_min_length}"
        )

        raise CabboException(
            f"Invalid phone number format for {country.name}. Example: {example}",
            status_code=422,
        )

    return country.phone_code + " " + num


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
            raise CabboException("Phone number is required for driver", status_code=400)

        if not payload.dob:
            raise CabboException(
                "Please enter the driver's date of birth so we can check if they meet the minimum age requirement.",
                status_code=400,
            )

    # Validate driver age
    if payload.dob:
        # Get age from dob
        age = calculate_age_from_dob(payload.dob)
        validate_driver_age_by_country(age=age, country=country)

    # Validate phone number
    payload.phone = validate_phone_by_country(phone=payload.phone, country=country)
    # Validate payment phone number
    if payload.payment_phone_number:
        payload.payment_phone_number = validate_phone_by_country(
            phone=payload.payment_phone_number, country=country
        )
    if not payload.payment_phone_number or payload.payment_phone_number.strip() == "":
        payload.payment_phone_number = (
            payload.phone
        )  # Use driver's primary phone number if alternate not provided

    # Validate emergency contact phone number
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
        # Get age from dob
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

    # Validate emergency contact phone number
    if (
        payload.emergency_contact_number
        and payload.emergency_contact_number.strip() != ""
    ):
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
    payload: Union[CustomerOTPRequest, CustomerOnboardInitiationRequest] = Body(...),
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
    payload: Union[CustomerLoginRequest, CustomerOnboardInitiationRequest] = Body(...),
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
        # Get age from dob
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


def _get_total_trip_days(start_date: datetime, end_date: datetime) -> int:
    total_seconds = (end_date - start_date).total_seconds()
    total_days = math.ceil(total_seconds / 86400)
    return total_days


