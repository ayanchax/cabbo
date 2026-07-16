from datetime import datetime, timedelta, timezone
import json
from typing import Literal, Optional, Union

from core.exceptions import CabboException, GENERIC_EXCEPTION
from core.security import RoleEnum, verify_hash
from core.store import ConfigStore
from core.trip_constants import TRIP_MESSAGES, TRIP_RESPONSE_OPTIONS
from core.trip_helpers import (
    attach_relationships_to_trip,
    generate_trip_field_dictionary,
    get_trip_type_id_by_trip_type,
)
from models.common import AppBackgroundTask
from models.customer.customer_orm import Customer
from models.pricing.pricing_schema import (
    TripPackageConfigSchema,
)
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_enums import (
    FuelTypeEnum,
    TripResponseView,
    TripStatusEnum,
    TripTypeEnum,
)
from models.trip.trip_orm import Trip, TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import (
    AdditionalDetailsOnTripStatusChange,
    TripBookRequest,
    TripDetailSchema,
    TripDetails,
    TripSearchRequest,
    TripUpdateRequestSchema,
)
from sqlalchemy.orm import Session

from models.user.user_orm import User
from services.cab_service import (
    get_recommended_car_type,
    remove_extra_fields_from_fleet,
    serialize_fleet,
)
from services.cancelation_service import serialize_cancelation
from services.configuration_service import (
    remove_extra_fields_from_currency,
    serialize_currency,
)
from services.customer_service import serialize_customer, serialize_customer_for_admin_retrieval
from services.dispute_service import serialize_dispute
from services.driver_service import remove_extra_fields_from_driver
from services.location_service import remove_extra_fields_from_location
from services.passenger_service import (
    get_passenger_id_from_preferences,
    populate_passenger_details,
    serialize_passenger,
    validate_passenger_id,
)
from services.policy_service import serialize_cancellation_and_refund_policy
from services.pricing_service import (
    get_driver_allowance,
    get_parking,
    get_tolls,
)
from services.trip_package_service import (
    remove_extra_fields_from_trip_package,
    serialize_trip_package,
)
from services.trip_type_service import (
    remove_extra_fields_from_trip_type,
    serialize_trip_type,
)
from services.trips.airport_transfers_service import remove_extra_fields_from_airport_transfer_trip
from services.trips.local_hourly_rental_service import (
    remove_extra_fields_from_local_hourly_rental_trip,
)
from services.trips.outstation_service import remove_extra_fields_from_outstation_trip
from services.trips.status_service import change_status
from services.validation_service import validate_serviceable_area, validate_trip_type
from utils.utility import remove_none_recursive, validate_date_time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, or_, select
from core.config import settings
import logging

log = logging.getLogger(__name__)


def serialize_trip(
    trip: Trip,
    view: TripResponseView = TripResponseView.ADMIN_DETAIL,
) -> dict:
    if not trip:
        raise CabboException(
            "Trip not found",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )
    options = TRIP_RESPONSE_OPTIONS.get(view, None)
    if not options:
        raise CabboException(
            f"Invalid trip response view: {view}",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )


    trip_dict = trip.__dict__.copy()  # Convert ORM object to a dictionary
    driver = trip_dict.get("driver")
    trip_type_master = trip_dict.get("trip_type_master")
    package = trip_dict.get("package")
    passenger = trip_dict.get("passenger")
    customer = trip_dict.get("customer")
    cancellation = trip_dict.get("cancellation")
    dispute = trip_dict.get("dispute")
    rating = trip_dict.get("trip_rating")

    if driver:  # Serialize the driver if it exists
        from services.driver_service import serialize_driver

        trip_dict = serialize_driver(driver, trip_dict)
    else:
        trip_dict["driver"] = None
    if trip_type_master:  # Serialize the trip type if it exists
        trip_dict = serialize_trip_type(trip_type_master, trip_dict)
    else:
        trip_dict["trip_type"] = None
    if package:  # Serialize the package if it exists
        trip_dict = serialize_trip_package(trip, trip_dict)
    else:
        trip_dict["package"] = None
    if passenger:  # Serialize the passenger if it exists
        trip_dict = serialize_passenger(passenger, trip_dict)
    else:
        trip_dict["passenger"] = (
            None  # means passenger is itself the customer, so we can populate customer details in the response if expose_customer_details is True
        )
     

    if options.expose_customer_details:
        if customer:
            if view == TripResponseView.ADMIN_LIST:
                trip_dict = serialize_customer_for_admin_retrieval(customer, trip_dict)
            else:
                trip_dict = serialize_customer(customer, trip_dict)

        else:
            trip_dict["customer"] = None
    if options.expose_cancellation_detail:
        if cancellation:
            trip_dict = serialize_cancelation(cancellation, trip_dict)
    if options.expose_dispute_details:
        if dispute:
            trip_dict = serialize_dispute(dispute, trip_dict)

    if options.expose_currency_detail:
        trip_dict = serialize_currency(trip_dict=trip_dict)
    if options.expose_fleet_detail:
        trip_dict = serialize_fleet(trip=trip, trip_dict=trip_dict)

    trip_type = (
        trip_dict.get("trip_type", {}).get("trip_type")
        if trip_dict.get("trip_type")
        else None
    )
    if trip_type and options.expose_policy_detail:
        trip_type = TripTypeEnum(trip_type)
        trip_dict = serialize_cancellation_and_refund_policy(
            trip=trip, trip_dict=trip_dict, trip_type=trip_type
        )

    trip_dict["rate_per_km"] = trip.rate_per_km if trip.rate_per_km else 0.0

    if options.expose_trip_label:
        trip_dict["label"] = get_trip_label(trip_dict)
    
    if options.expose_trip_review:
        from services.trip_review_service import serialize_rating
        trip_dict = serialize_rating(trip_dict=trip_dict)
           
            
    # Remove SQLAlchemy instance state which is not serializable and can cause issues during response serialization
    trip_dict.pop("_sa_instance_state", None)
    trip_details = TripDetailSchema.model_validate(trip_dict).model_dump(
        exclude_none=True
    )
    if options.optimize_response:
        if trip_type:
            trip_type = TripTypeEnum(trip_type)
            currency = trip_dict.get("currency", {})
            if currency:
                trip_details["currency"] = remove_extra_fields_from_currency(
                    trip_details["currency"]
                )

            origin = trip_dict.get("origin", {})
            if origin:
                trip_details["origin"] = remove_extra_fields_from_location(
                    trip_details["origin"]
                )

            destination = trip_dict.get("destination", {})
            if destination:
                trip_details["destination"] = remove_extra_fields_from_location(
                    trip_details["destination"]
                )

            fleet = trip_dict.get("fleet", {})
            if fleet:
                trip_details["fleet"] = remove_extra_fields_from_fleet(
                    trip_details["fleet"]
                )

            package = trip_dict.get("package", {})
            if package:
                trip_details["package"] = remove_extra_fields_from_trip_package(
                    trip_details["package"]
                )

            trip_type_data = trip_dict.get("trip_type", {})
            if trip_type_data:
                trip_details["trip_type"] = remove_extra_fields_from_trip_type(
                    trip_details["trip_type"]
                )

            if trip_type == TripTypeEnum.local:
                trip_details = remove_extra_fields_from_local_hourly_rental_trip(
                    trip_details
                )
            elif trip_type == TripTypeEnum.outstation:
                trip_details = remove_extra_fields_from_outstation_trip(trip_details)
            elif trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
                trip_details = remove_extra_fields_from_airport_transfer_trip(trip_details, trip_type)
        
        if trip_details.get("driver"):
            trip_details["driver"] = remove_extra_fields_from_driver(
                driver_details=trip_details["driver"]
            )

    return remove_none_recursive(trip_details)


def _get_trip_type_by_trip_type_id(trip_type_id: str, db: Session) -> TripTypeEnum:
    """
    Retrieves the trip type from the database based on the provided trip type ID.
    Args:
        trip_type_id (str): The ID of the trip type to retrieve.
        db (Session): The database session for ORM operations.
    Returns:
        TripTypeEnum: The trip type corresponding to the provided ID.
    Raises:
        CabboException: If the trip type ID is not found in the database.
    """
    trip_type_obj = (
        db.query(TripTypeMaster).filter(TripTypeMaster.id == trip_type_id).first()
    )
    if not trip_type_obj:
        raise CabboException(
            f"Trip type with ID {trip_type_id} not found",
            status_code=404,
            error_code=GENERIC_EXCEPTION,
        )
    return TripTypeEnum(trip_type_obj.trip_type)


def _retrieve_trip_package_by_id(
    package_id: str,
    db: Session,
    fallback_duration: int = 4,
    fallback_km: int = 40,
    fallback_label: str = "4Hours / 40KM",
):
    if not package_id:
        return TripPackageConfigSchema(
            included_hours=fallback_duration,
            included_km=fallback_km,
            package_label=fallback_label,
        )
    package = (
        db.query(TripPackageConfig)
        .filter(TripPackageConfig.id == package_id, TripPackageConfig.is_active == True)
        .first()
    )
    if not package:
        return TripPackageConfigSchema(
            included_hours=fallback_duration,
            included_km=fallback_km,
            package_label=fallback_label,
        )
    package_schema = TripPackageConfigSchema.model_validate(package)
    return (
        package_schema
        if package_schema.included_hours and package_schema.included_hours > 0
        else TripPackageConfigSchema(
            included_hours=fallback_duration,
            included_km=fallback_km,
            package_label=fallback_label,
        )
    )


def _calculate_expected_trip_end_datetime(
    trip_type: TripTypeEnum,
    start_date: datetime,
    end_date: datetime,
    db: Session,
    package_id: str = None,
) -> datetime:
    """
    Calculates the expected end datetime for a trip based on the trip type, start date, end date, and package ID.
    Args:
        trip_type (TripTypeEnum): The type of trip (local, outstation, airport).
        start_date (datetime): The start date of the trip.
        end_date (datetime): The end date of the trip.
        package_id (str): The package ID if applicable.
    Returns:
        datetime: The expected end datetime for the trip.
    """
    if trip_type == TripTypeEnum.local:
        # For local trips, retrieve the package duration if available, otherwise default to 6 hours
        if package_id:
            package = _retrieve_trip_package_by_id(package_id=package_id, db=db)
            if package and package.included_hours:
                return start_date + timedelta(hours=package.included_hours)
        return start_date + timedelta(hours=4)  # Default to 4 hours for local trips

    elif trip_type == TripTypeEnum.outstation:
        # For outstation trips, use the provided end date
        return end_date

    elif trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        # For airport trips, we can assume a short duration
        return start_date + timedelta(hours=1)  # Default to 1 hour for airport trips
    else:
        raise CabboException(
            f"Trip type {trip_type} is not supported for expected end datetime calculation",
            status_code=501,
            error_code=GENERIC_EXCEPTION,
        )


def get_trip_messages(status: Union[str, TripStatusEnum]):
    status = status.value if isinstance(status, TripStatusEnum) else status
    return TRIP_MESSAGES.get(status, {})


def _set_default_preferences(search_in: TripSearchRequest):
    """
    Ensures all required trip search preferences have sensible defaults.

    - Sets 'preferred_car_type' based on passenger and luggage totals.
    - Sets 'preferred_fuel_type' to FuelTypeEnum.diesel if not provided.
    - Ensures at least one adult is present (defaults to 1 if missing or < 1).
    - Ensures number of children is not negative (defaults to 0 if missing or < 0).

    Args:
        search_in (TripSearchRequest): The trip search request object to populate defaults for.
    """

    if search_in.num_adults is None or search_in.num_adults < 1:
        search_in.num_adults = 1  # Ensure at least one adult is present
    if search_in.num_children is None or search_in.num_children < 0:
        search_in.num_children = 0

    if not search_in.preferred_fuel_type:
        search_in.preferred_fuel_type = FuelTypeEnum.diesel
    total_num_people = search_in.total_passengers
    total_num_luggages = search_in.total_luggages
    search_in.preferred_car_type = get_recommended_car_type(
        total_num_people=total_num_people,
        total_num_luggages=total_num_luggages,
    )


def verify_trip_hash(booking_request: TripBookRequest):
    if not hasattr(booking_request, "option"):
        raise CabboException(
            "Invalid booking request, option is required",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )

    if not booking_request.option or not hasattr(booking_request.option, "hash"):
        raise CabboException(
            "Invalid booking request, option hash is required",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    if not booking_request.preferences:
        raise CabboException(
            "Invalid booking request, preferences are required",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    # Validate the trip option hash
    option_dict, preference_dict = generate_trip_field_dictionary(
        search_in=booking_request.preferences,
        car_type=booking_request.option.car_type,
        fuel_type=booking_request.option.fuel_type,
        option=booking_request.option,
    )
    payload = json.dumps(
        {"option": option_dict, "preferences": preference_dict}, sort_keys=True
    )

    if not verify_hash(
        payload=payload,
        client_hash=booking_request.option.hash,
    ):
        raise CabboException(
            "Invalid booking request, option hash is not valid",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )


def validate_trip_search(
    search_in: TripSearchRequest, requestor: str, db: Session, config_store: ConfigStore
):

    # Validate passenger ID if provided
    validate_passenger_id(search_in, requestor, db)

    # Ensure all required trip search preferences have sensible defaults
    _set_default_preferences(search_in)

    # Enforce serviceable area boundaries
    validate_serviceable_area(search_in=search_in, config_store=config_store, db=db)

    trip_type = search_in.trip_type
    # Validate trip type
    validate_trip_type(trip_type, config_store=config_store)


def delete_temp_trip(requestor: str, db: Session):
    """
    Deletes all temporary trip details for the given requestor.
    We delete all temporary trip records for the requestor to ensure no stale temporary data remains in the system.
    Args:
        requestor (str): The user or system initiating the deletion.
        db (Session): The database session for ORM operations.
    """
    try:
        # Delete all temporary trip records for the requestor
        db.query(TempTrip).filter(TempTrip.creator_id == requestor).delete()
        db.commit()
        log.info(f"Temporary trip details deleted for requestor: {requestor}")
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Failed to delete temporary trip details: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


def create_temporary_trip(
    booking_request: TripBookRequest, requestor: str, db: Session
) -> TempTrip:
    """

    Creates a temporary trip record in the database based on the booking request.
    This function validates the booking request, calculates necessary fields, and stores the trip details.
    Args:
        booking_request (TripBookRequest): The trip booking request containing preferences and options.
        requestor (str): The user or system initiating the trip creation.
        db (Session): The database session for ORM operations.
    Returns:
        TempTrip: The created temporary trip record.
    Raises:
        CabboException: If the booking request is invalid or if any database operation fails.
    """
    trip_type_id = get_trip_type_id_by_trip_type(
        booking_request.preferences.trip_type, db=db
    )
    validated_start_date = validate_date_time(
        date_time=booking_request.preferences.start_date,
        timezone_str=(
            booking_request.metadata.timezone
            if booking_request.metadata and booking_request.metadata.timezone
            else settings.CABBO_DEFAULT_TIMEZONE
        ),
    )

    validated_end_date = None
    if booking_request.preferences.end_date:
        validated_end_date = validate_date_time(
            date_time=booking_request.preferences.end_date,
            timezone_str=(
                booking_request.metadata.timezone
                if booking_request.metadata and booking_request.metadata.timezone
                else settings.CABBO_DEFAULT_TIMEZONE
            ),
        )

    json_hops = (
        [hop.model_dump() for hop in booking_request.preferences.hops]
        if booking_request.preferences.hops
        else None
    )
    temp_trip = TempTrip(
        creator_id=requestor,
        trip_type_id=trip_type_id,
        origin=booking_request.preferences.origin.model_dump(),
        destination=booking_request.preferences.destination.model_dump(),
        hops=json_hops,
        is_interstate=(
            booking_request.metadata.is_interstate
            if booking_request.preferences.trip_type == TripTypeEnum.outstation
            else False
        ),
        is_round_trip=(
            booking_request.metadata.is_round_trip
            if hasattr(booking_request.metadata, "is_round_trip")
            else False
        ),
        total_unique_states=(
            booking_request.metadata.total_unique_states
            if booking_request.preferences.trip_type == TripTypeEnum.outstation
            else None
        ),
        unique_states=(
            booking_request.metadata.unique_states
            if booking_request.preferences.trip_type == TripTypeEnum.outstation
            else None
        ),
        package_id=(
            booking_request.preferences.package_id
            if booking_request.preferences.trip_type == TripTypeEnum.local
            and booking_request.preferences.package_id
            else None
        ),
        package_label=(
            booking_request.option.package if booking_request.option.package else None
        ),
        package_label_short=(
            booking_request.option.package_short_label
            if booking_request.option.package_short_label
            else None
        ),
        start_datetime=validated_start_date,
        end_datetime=validated_end_date,
        expected_end_datetime=_calculate_expected_trip_end_datetime(
            booking_request.preferences.trip_type,
            validated_start_date,
            validated_end_date,
            db,
            booking_request.preferences.package_id,
        ),
        total_days=(
            booking_request.metadata.total_trip_days
            if hasattr(booking_request.metadata, "total_trip_days")
            else None
        ),
        included_kms=(
            booking_request.metadata.included_kms
            if hasattr(booking_request.metadata, "included_kms")
            else None
        ),
        num_adults=booking_request.preferences.num_adults,
        num_children=booking_request.preferences.num_children,
        num_passengers=booking_request.preferences.total_passengers,
        num_large_suitcases=booking_request.preferences.num_large_suitcases,
        num_carryons=booking_request.preferences.num_carryons,
        num_backpacks=booking_request.preferences.num_backpacks,
        num_other_bags=booking_request.preferences.num_other_bags,
        num_luggages=booking_request.preferences.total_luggages,
        preferred_car_type=booking_request.preferences.preferred_car_type,
        preferred_fuel_type=booking_request.preferences.preferred_fuel_type,
        in_car_amenities=(
            booking_request.metadata.in_car_amenities.model_dump()
            if booking_request.metadata.in_car_amenities
            else None
        ),
        price_breakdown=(
            booking_request.option.price_breakdown.model_dump()
            if booking_request.option.price_breakdown
            else None
        ),
        overages=(
            booking_request.option.overages.model_dump()
            if booking_request.option.overages
            else None
        ),
        rate_per_min=(
            booking_request.option.rate_per_min
            if booking_request.option.rate_per_min
            else 0.0
        ),
        rate_per_km=(
            booking_request.option.rate_per_km
            if booking_request.option.rate_per_km
            else 0.0
        ),
        base_fare=booking_request.option.price_breakdown.base_fare,
        driver_allowance=(
            get_driver_allowance(option=booking_request.option)
            if booking_request.preferences.trip_type
            in [TripTypeEnum.outstation, TripTypeEnum.local]
            else 0.0
        ),
        tolls=get_tolls(booking_request=booking_request),
        parking=get_parking(booking_request=booking_request),
        permit_fee=(
            booking_request.option.price_breakdown.permit_fee
            if booking_request.metadata.is_interstate
            and booking_request.option.price_breakdown.permit_fee
            else 0.0
        ),
        platform_fee=(
            booking_request.option.price_breakdown.platform_fee
            if booking_request.option.price_breakdown.platform_fee
            else 0.0
        ),
        final_price=booking_request.option.total_price,
        final_display_price=(
            booking_request.option.total_price
            - booking_request.option.price_breakdown.platform_fee
        ),
        inclusions=(
            booking_request.metadata.inclusions
            if booking_request.metadata.inclusions
            else None
        ),
        exclusions=(
            booking_request.metadata.exclusions
            if booking_request.metadata.exclusions
            else None
        ),
        flight_number=(
            booking_request.preferences.flight_number
            if booking_request.preferences and booking_request.preferences.flight_number
            else None
        ),
        terminal_number=(
            booking_request.preferences.terminal_number
            if booking_request.preferences
            and booking_request.preferences.terminal_number
            else None
        ),
        toll_road_preferred=(
            booking_request.preferences.toll_road_preferred
            if booking_request.preferences
            and booking_request.preferences.toll_road_preferred
            else False
        ),
        placard_required=(
            booking_request.preferences.placard_required
            if booking_request.preferences
            and booking_request.preferences.placard_required
            else False
        ),
        placard_name=(
            booking_request.preferences.placard_name
            if booking_request.preferences
            and booking_request.preferences.placard_required
            and booking_request.preferences.placard_name
            else None
        ),
        estimated_km=(
            booking_request.metadata.estimated_km
            if booking_request.metadata and booking_request.metadata.estimated_km
            else 0.0
        ),
        indicative_overage_warning=(
            booking_request.option.overages.indicative_overage_warning
            if booking_request.option.overages.indicative_overage_warning
            else None
        ),
        alternate_customer_phone=None,
        passenger_id=get_passenger_id_from_preferences(
            preferences=booking_request.preferences
        ),
        hash=(
            booking_request.option.hash
            if hasattr(booking_request.option, "hash")
            else None
        ),
        timezone=(
            booking_request.metadata.timezone
            if hasattr(booking_request.metadata, "timezone")
            else settings.CABBO_DEFAULT_TIMEZONE
        ),
        utc_offset=(
            booking_request.metadata.utc_offset
            if hasattr(booking_request.metadata, "utc_offset")
            else settings.CABBO_DEFAULT_UTC_OFFSET
        ),
    )
    try:
        db.add(temp_trip)
        db.commit()
        db.refresh(temp_trip)
        log.info(f"Temporary trip created for requestor: {requestor}")
        return temp_trip
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Failed to create temporary trip: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


def populate_trip_schema(trip: Union[Trip, TempTrip], db: Session) -> TripDetails:
    trip_schema = TripDetails.model_validate(
        trip
    )  # Convert Trip object to TripDetail schema
    trip_schema.trip_type = _get_trip_type_by_trip_type_id(
        trip_type_id=trip.trip_type_id, db=db
    )

    passenger = populate_passenger_details(passenger_id=trip.passenger_id, db=db)
    if passenger:
        trip_schema.passenger = passenger
    result = trip_schema.model_dump(
        exclude_none=True
    )  # Return the trip schema as a dictionary excluding None values
    return remove_none_recursive(result)


def get_trip_by_id(trip_id: str, db: Session) -> Trip:
    """Retrieve a trip by its ID."""
    return db.query(Trip).filter(Trip.id == trip_id).first()


async def async_get_trip_by_id(
    trip_id: str,
    db: AsyncSession,
    view: TripResponseView = TripResponseView.ADMIN_DETAIL,
) -> Trip:
    """Asynchronously retrieve a trip by its ID."""
    query = select(Trip).filter(
        Trip.id == trip_id, Trip.is_active == True
    )  # Only retrieve active trips
    result = await db.execute(query)
    trip_result = result.scalars().first()
    if trip_result:
        await attach_relationships_to_trip(
            trip_result,
            db,
            view=view,
        )
    return trip_result


async def async_get_trip_by_booking_id(
    booking_id: str,
    db: AsyncSession,
    view: TripResponseView = TripResponseView.ADMIN_DETAIL,
) -> Trip:
    """Asynchronously retrieve a trip by its booking ID."""
    result = await db.execute(
        select(Trip).filter(Trip.booking_id == booking_id, Trip.is_active == True)
    )  # Only retrieve active trips
    trip_result = (
        result.scalars().one_or_none()
    )  # Always returns one result or None, as booking_id is unique. Raises an error if multiple results are found, which should not happen.
    if trip_result:
        await attach_relationships_to_trip(
            trip_result,
            db,
            view=view,
        )
    return trip_result


async def async_get_trip_by_booking_id_customer_id(
    booking_id: str,
    customer_id: str,
    db: AsyncSession,
    view: TripResponseView = TripResponseView.CUSTOMER_DETAIL,
) -> Trip:
    """Asynchronously retrieve a trip by its booking ID and customer ID."""
    result = await db.execute(
        select(Trip).filter(
            Trip.booking_id == booking_id,
            Trip.creator_id == customer_id,
            Trip.creator_type == RoleEnum.customer,
            Trip.is_active == True,
        )
    )  # Only retrieve active trips
    trip_result = result.scalars().one_or_none()
    if trip_result:
        await attach_relationships_to_trip(
            trip_result,
            db,
            view=view,
        )
    return trip_result


async def async_get_all_trips(db: AsyncSession) -> list[Trip]:
    """Asynchronously retrieve all trips."""
    result = await db.execute(
        select(Trip).filter(Trip.is_active == True)
    )  # Only retrieve active trips
    all = result.scalars().all()
    for trip in all:
        await attach_relationships_to_trip(trip, db, view=TripResponseView.ADMIN_LIST)
    return all


async def async_get_all_trips_paginated(
    db: AsyncSession,
    page: int = 1,
    limit: int = 10,
    view: TripResponseView = TripResponseView.ADMIN_LIST,
) -> dict:
    """Asynchronously retrieve all active trips with pagination."""
    page = max(page, 1)
    limit = max(limit, 1)
    offset = (page - 1) * limit

    base_filters = [Trip.is_active == True]

    count_result = await db.execute(
        select(func.count(Trip.id)).filter(*base_filters)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Trip)
        .filter(*base_filters)
        .order_by(Trip.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    trips = result.scalars().all()
    for trip in trips:
        await attach_relationships_to_trip(trip, db, view=view)

    return {
        "items": trips,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
            "has_next": offset + len(trips) < total,
            "has_previous": page > 1,
        },
    }


async def async_get_trips_by_driver_id(driver_id: str, db: AsyncSession) -> list[Trip]:
    """Asynchronously retrieve trips by driver ID."""
    query = select(Trip).filter(
        Trip.driver_id == driver_id, Trip.is_active == True
    )  # Only retrieve active trips
    result = await db.execute(query)
    trips = result.scalars().all()
    if not trips:
        return []
    for trip in trips:
        await attach_relationships_to_trip(trip, db, view=TripResponseView.ADMIN_LIST)
    return trips


def serialize_trips(trips: list[Trip], view: TripResponseView) -> list:
    serialized_trips = []
    for trip in trips:
        serialized_trips.append(
            serialize_trip(
                trip, view=view
                 
            )
        )
    return serialized_trips


def remove_platform_payment_fields_for_admin_trip_operations(
    trips: list[dict],
) -> list[dict]:
    """Hide platform payment internals from admin trip operation list responses."""
    for trip in trips:
        trip["cost_to_driver"] = trip.get("balance_payment", 0.0) #Balance payment is the amount left to pay which is the actual driver payment for this trip plus any extras as applicable.
        trip.pop("advance_payment", None)
        trip.pop("balance_payment", None)
        trip.pop("base_fare", None)
        trip.pop("final_price", None)


        price_breakdown = trip.get("price_breakdown")
        if isinstance(price_breakdown, dict):
            price_breakdown.pop("platform_fee", None)

    return trips


async def async_get_trips_by_customer_id(
    customer_id: str,
    db: AsyncSession,
    view: TripResponseView = TripResponseView.CUSTOMER_LIST,
) -> list[Trip]:
    """Asynchronously retrieve trips by customer ID."""
    result = await db.execute(
        select(Trip).filter(
            Trip.creator_id == customer_id,
            Trip.creator_type == RoleEnum.customer,
            Trip.is_active == True,
        )
    )  # Only retrieve active trips
    trips = result.scalars().all()
    if not trips:
        return []
    for trip in trips:
        await attach_relationships_to_trip(
            trip,
            db,
            view=view,
        )
    return trips


async def async_get_trips_by_customer_id_paginated(
    customer_id: str,
    db: AsyncSession,
    bucket: Literal["upcoming", "ongoing", "past"] = "upcoming",
    page: int = 1,
    limit: int = 10,
    view: TripResponseView = TripResponseView.CUSTOMER_LIST_SELF,
) -> dict:
    """Asynchronously retrieve customer trips by UI bucket with pagination."""
    page = max(page, 1)
    limit = max(limit, 1)
    offset = (page - 1) * limit # Calculate the offset for pagination, meaning starting from the (page-1)*limit-th record for the current page.

    current_datetime = datetime.now(timezone.utc).replace(tzinfo=None)

    one_day_ago = current_datetime - timedelta(hours=24)

    base_filters = [
        Trip.creator_id == customer_id,
        Trip.creator_type == RoleEnum.customer,
        Trip.is_active == True,
    ]

    airport_and_local_types = [
        TripTypeEnum.airport_pickup,
        TripTypeEnum.airport_drop,
        TripTypeEnum.local,
    ]

    if bucket == "upcoming":
        bucket_filter = or_(
            and_(
                TripTypeMaster.trip_type.in_(airport_and_local_types),
                Trip.status.in_([TripStatusEnum.confirmed, TripStatusEnum.created]),
                Trip.start_datetime > current_datetime,
            ),
            and_(
                TripTypeMaster.trip_type == TripTypeEnum.outstation,
                Trip.status.in_([TripStatusEnum.confirmed, TripStatusEnum.created]),
                Trip.start_datetime > current_datetime,
                Trip.expected_end_datetime > current_datetime,
            ),
        )
        order_by = Trip.start_datetime.asc()
    elif bucket == "ongoing":
        bucket_filter = or_(
            and_(
                TripTypeMaster.trip_type.in_(airport_and_local_types),
                Trip.status == TripStatusEnum.ongoing,
                Trip.start_datetime <= current_datetime,
                Trip.start_datetime >= one_day_ago,
            ),
            and_(
                TripTypeMaster.trip_type == TripTypeEnum.outstation,
                Trip.status == TripStatusEnum.ongoing,
                Trip.start_datetime <= current_datetime,
                Trip.expected_end_datetime >= current_datetime,
            ),
        )
        order_by = Trip.start_datetime.asc()
    else:
        bucket_filter = or_(
            Trip.status.in_(
                [
                    TripStatusEnum.completed,
                    TripStatusEnum.cancelled,
                    TripStatusEnum.dispute,
                ]
            ),
            and_(
                TripTypeMaster.trip_type.in_(airport_and_local_types),
                Trip.status.in_([TripStatusEnum.confirmed, TripStatusEnum.created]),
                Trip.start_datetime <= current_datetime,
            ), #stale expired airport and local trips that are still marked as confirmed or created but have a start datetime in the past should be considered past trips
            and_(
                TripTypeMaster.trip_type == TripTypeEnum.outstation,
                Trip.status.in_([TripStatusEnum.confirmed, TripStatusEnum.created]),
                Trip.start_datetime <= current_datetime,
                Trip.expected_end_datetime <= current_datetime,
            ), #stale expired outstation trips that are still marked as confirmed or created but have a start datetime in the past and expected end datetime in the past should be considered past trips
        )
        order_by = Trip.start_datetime.desc()

    j = (TripTypeMaster, Trip.trip_type_id == TripTypeMaster.id)
    f = (*base_filters, bucket_filter)
    count_result = await db.execute(
        select(func.count(Trip.id))
        .join(*j)
        .filter(*f)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(Trip)
        .join(*j)
        .filter(*f)
        .order_by(order_by)
        .offset(offset) #start cursor from offset, which is calculated based on the current page and limit, ensuring that we skip the appropriate number of records for pagination
        .limit(limit) #upto 'limit' number of records for the current page, ensuring that we only retrieve the desired number of trips for the current page
    )
    trips = result.scalars().all()
    for trip in trips:
        await attach_relationships_to_trip(
            trip,
            db,
            view=view,
        )

    return {
        "bucket": bucket,
        "items": trips,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": (total + limit - 1) // limit,
            "has_next": offset + len(trips) < total,
            "has_previous": page > 1,
        },
    }



def group_by_trip_status(trips: list[dict], validate_by_tz: bool = False) -> dict:
    if validate_by_tz:
        log.info("Grouping trips by status with timezone validation")
        return _group_by_trip_status_with_timezone_validation(trips)
    log.info("Grouping trips by status without timezone validation")
    upcoming_trips = [
        trip
        for trip in trips
        if trip.get("status")
        in [TripStatusEnum.confirmed.value, TripStatusEnum.created.value]
    ]
    ongoing_trips = [
        trip for trip in trips if trip.get("status") == TripStatusEnum.ongoing.value
    ]
    past_trips = [
        trip
        for trip in trips
        if trip.get("status")
        in [TripStatusEnum.completed.value, TripStatusEnum.cancelled.value, TripStatusEnum.dispute.value]
    ]
    return {"upcoming": upcoming_trips, "ongoing": ongoing_trips, "past": past_trips}


def get_trip_label(trip: dict):
    try:
        current_datetime = datetime.now(timezone.utc)

        trip_status = trip.get("status")
        trip_type = (
            trip.get("trip_type").get("trip_type") if trip.get("trip_type") else None
        )

        trip_type = TripTypeEnum(trip_type) if trip_type else None
        trip_status = TripStatusEnum(trip_status) if trip_status else None
        if not trip_type or not trip_status:
            return "unknown"
        start_datetime = trip.get("start_datetime")
        expected_end_datetime = trip.get("expected_end_datetime")

        # Ensure start_datetime and expected_end_datetime are timezone-aware
        start_datetime = (
            validate_date_time(start_datetime, timezone_str="UTC")
            if start_datetime
            else None
        )
        expected_end_datetime = (
            validate_date_time(expected_end_datetime, timezone_str="UTC")
            if expected_end_datetime
            else None
        )

        if trip_status in [
            TripStatusEnum.completed,
            TripStatusEnum.cancelled,
            TripStatusEnum.dispute,
        ]:
            # Terminal statuses should be labeled by lifecycle state regardless of
            # whether the scheduled trip time is still in the future.
            return trip_status.value

        # Airport Pickup, Drop, Rental Logic (1 day buffer for ongoing trips to account for delays and real-world conditions)
        if trip_type in [
            TripTypeEnum.airport_pickup,
            TripTypeEnum.airport_drop,
            TripTypeEnum.local,
        ]:
            if (
                trip_status in [TripStatusEnum.confirmed, TripStatusEnum.created]
                and start_datetime > current_datetime
            ):
                return "upcoming"
            elif (
                trip_status == TripStatusEnum.ongoing
                and start_datetime <= current_datetime
                and start_datetime >= (current_datetime - timedelta(hours=24))
            ):
                return "ongoing"
            elif (
                trip_status
                in [
                    TripStatusEnum.completed,
                    TripStatusEnum.cancelled,
                    TripStatusEnum.confirmed,
                    TripStatusEnum.created,
                ]
                and start_datetime <= current_datetime
            ):  # All trips that have started but are not ongoing should be categorized as past, including those that are completed, cancelled, or even those that are still marked as confirmed or created but have a start datetime in the past. This accounts for real-world scenarios where there might be delays in status updates or early arrivals.
                if trip_status == TripStatusEnum.completed:
                    return "completed"
                elif trip_status == TripStatusEnum.cancelled:
                    return "cancelled"
                return "past"

        # Outstation Logic(strictly based on start and expected end datetime to account for real-world conditions like delays, early arrivals, etc.)
        elif trip_type == TripTypeEnum.outstation:
            if (
                trip_status in [TripStatusEnum.confirmed, TripStatusEnum.created]
                and start_datetime > current_datetime
                and expected_end_datetime > current_datetime
            ):
                return "upcoming"
            elif (
                trip_status == TripStatusEnum.ongoing
                and start_datetime <= current_datetime
                and expected_end_datetime >= current_datetime
            ):
                return "ongoing"
            elif (
                trip_status
                in [
                    TripStatusEnum.completed,
                    TripStatusEnum.cancelled,
                    TripStatusEnum.confirmed,
                    TripStatusEnum.created,
                ]
                and start_datetime <= current_datetime
                and expected_end_datetime <= current_datetime
            ):  # All outstation trips that have started but are not ongoing should be categorized as past, including those that are completed, cancelled, or even those that are still marked as confirmed or created but have a start datetime in the past. This accounts for real-world scenarios where there might be delays in status updates or early arrivals.
                if trip_status == TripStatusEnum.completed:
                    return "completed"
                elif trip_status == TripStatusEnum.cancelled:
                    return "cancelled"
                else:
                    return "past"

        return "unknown"
    except Exception as e:
        log.error(
            f"Error determining trip label for trip ID {trip.get('id')}: {str(e)}"
        )
        return "unknown"


def _group_by_trip_status_with_timezone_validation(trips: list[dict]) -> dict:
    upcoming_trips = []
    ongoing_trips = []
    past_trips = []
    try:
        for trip in trips:
            label = get_trip_label(trip)
            if label == "upcoming":
                upcoming_trips.append(trip)
            elif label == "ongoing":
                ongoing_trips.append(trip)
            elif label == "past" or label in ["completed", "cancelled", "dispute"]:
                past_trips.append(trip)
    except Exception as e:
        log.error(f"Error grouping trips by status with timezone validation: {str(e)}")
    return {"upcoming": upcoming_trips, "ongoing": ongoing_trips, "past": past_trips}


async def update_trip_status(
    trip_id: str,
    db: AsyncSession,
    new_status: TripStatusEnum,
    requestor: Union[User, Customer],
    payload: AdditionalDetailsOnTripStatusChange = None,
    validate_time_window: bool = False,
):
    trip = await async_get_trip_by_id(trip_id, db, view=TripResponseView.ADMIN_DETAIL)
    if trip is None:
        raise CabboException(
            "Trip not found", status_code=404, error_code=GENERIC_EXCEPTION
        )

    allowed_status_transitions = {
        TripStatusEnum.confirmed: [TripStatusEnum.ongoing, TripStatusEnum.cancelled],
        TripStatusEnum.ongoing: [TripStatusEnum.completed, TripStatusEnum.dispute],
        TripStatusEnum.completed: [],
        TripStatusEnum.cancelled: [],
        TripStatusEnum.dispute: [],
    }
    # Out of confirmed, ongoing, completed, canceled and dispute, a trip gets confirmed only from the #booking_service.py confirm_trip_booking() method.
    if new_status not in allowed_status_transitions.get(
        TripStatusEnum(trip.status), []
    ):
        raise CabboException(
            f"Invalid status transition from {trip.status} to {new_status.value}.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    trip_schema: TripDetailSchema = None
    background_task: Optional[AppBackgroundTask] = None
    try:
        trip_schema, background_task = await change_status(
            trip=trip,
            db=db,
            status=new_status,
            requestor=requestor,
            payload=payload,
            validate_time_window=validate_time_window,
        )
    except CabboException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to update trip status: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )

    return trip_schema, background_task


async def delete_trip(trip_id: str, db: AsyncSession):
    trip = await async_get_trip_by_id(trip_id, db)
    if not trip:
        raise CabboException(
            "Trip not found", status_code=404, error_code=GENERIC_EXCEPTION
        )
    try:
        trip.is_active = False  # Soft delete by marking the trip as inactive
        await db.commit()
        return {"message": "Trip deleted successfully"}
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to delete trip: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def activate_trip(trip_id: str, db: AsyncSession):
    try:
        query = select(Trip).filter(Trip.id == trip_id)
        result = await db.execute(query)
        trip = result.scalars().first()
        if not trip:
            raise CabboException(
                "Trip not found", status_code=404, error_code=GENERIC_EXCEPTION
            )
        if trip.is_active:
            raise CabboException(
                "Trip is already active", status_code=400, error_code=GENERIC_EXCEPTION
            )

        trip.is_active = True  # Activate the trip by marking it as active
        await db.commit()
        await db.refresh(trip)
        return {"message": f"Trip with id {trip_id} has been activated successfully."}

    except CabboException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to activate trip: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )


async def update_non_cost_impacting_trip_fields(
    trip: Trip,
    db: AsyncSession,
    payload: TripUpdateRequestSchema,
    validate_status: bool = False,
):
    """
    Updates non-cost impacting fields of a trip such as flight number, terminal number, and in-car amenities.
    This function can be used to update trip details without affecting the pricing or cost calculations.

    Args:
        trip (Trip): The trip object to be updated.
        db (AsyncSession): The database session for ORM operations.
        update_data (TripUpdateRequestSchema): The data to update the trip with.
        validate_status (bool): Whether to validate the trip status before allowing updates. Defaults to False.
    """
    try:
        if validate_status and trip.status not in [TripStatusEnum.confirmed, TripStatusEnum.created]:
            raise CabboException(
                f"Trip details can only be updated for trips in confirmed or created status. Current status: {trip.status}",
                status_code=400,
            )
        if trip.trip_type_master.trip_type in [
            TripTypeEnum.airport_pickup,
            TripTypeEnum.airport_drop,
        ]:
            if payload.flight_number is not None:
                trip.flight_number = payload.flight_number
            if payload.terminal_number is not None:
                trip.terminal_number = payload.terminal_number
            if trip.placard_required and payload.placard_name is not None:
                trip.placard_name = payload.placard_name

        if payload.alternate_customer_phone is not None:
            trip.alternate_customer_phone = payload.alternate_customer_phone

        if payload.special_needs_requests is not None:
            trip.special_needs_requests = payload.special_needs_requests

        await db.commit()
        await db.refresh(trip)
        return True
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to update trip details: {str(e)}",
            status_code=500,
            error_code=GENERIC_EXCEPTION,
        )
