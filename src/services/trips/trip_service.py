from datetime import datetime, timedelta
import json
from typing import Union
from core.exceptions import CabboException
from core.security import verify_hash
from core.store import ConfigStore
from core.trip_constants import TRIP_MESSAGES
from core.trip_helpers import generate_trip_field_dictionary, get_trip_type_id_by_trip_type
from models.pricing.pricing_schema import (
    TripPackageConfigSchema,
)
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_enums import (
    CarTypeEnum,
    FuelTypeEnum,
    TripStatusEnum,
    TripTypeEnum,
)
from models.trip.trip_orm import Trip, TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import (
    TripBookRequest,
    TripDetails,
    TripSearchRequest,
)
from sqlalchemy.orm import Session

from services.passenger_service import (
    get_passenger_id_from_preferences,
    populate_passenger_details,
    validate_passenger_id,
)
from services.pricing_service import (
    get_driver_allowance,
    get_parking,
    get_tolls,
)
from services.validation_service import validate_serviceable_area, validate_trip_type
from utils.utility import remove_none_recursive, validate_date_time


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
            f"Trip type with ID {trip_type_id} not found", status_code=404
        )
    return TripTypeEnum(trip_type_obj.trip_type)



def _get_total_num_luggages(booking_request: TripBookRequest) -> int:
    """
    Calculates the total number of luggages based on the booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing luggage details.
    Returns:
        int: The total number of luggages.
    """
    return (
        booking_request.preferences.num_large_suitcases
        + booking_request.preferences.num_carryons
        + booking_request.preferences.num_backpacks
        + booking_request.preferences.num_other_bags
    )


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
        db.query(TripPackageConfig).filter(TripPackageConfig.id == package_id).first()
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
        )


def get_trip_messages(status: Union[str, TripStatusEnum]):
    status = status.value if isinstance(status, TripStatusEnum) else status
    return TRIP_MESSAGES.get(status, {})


def _set_default_preferences(search_in: TripSearchRequest):
    """
    Ensures all required trip search preferences have sensible defaults.

    - Sets 'preferred_car_type' to CarTypeEnum.sedan if not provided.
    - Sets 'preferred_fuel_type' to FuelTypeEnum.diesel if not provided.
    - Ensures at least one adult is present (defaults to 1 if missing or < 1).
    - Ensures number of children is not negative (defaults to 0 if missing or < 0).

    Args:
        search_in (TripSearchRequest): The trip search request object to populate defaults for.
    """
    if not search_in.preferred_car_type:
        search_in.preferred_car_type = CarTypeEnum.sedan
    if not search_in.preferred_fuel_type:
        search_in.preferred_fuel_type = FuelTypeEnum.diesel
    if search_in.num_adults < 1 or search_in.num_adults is None:
        search_in.num_adults = 1  # Ensure at least one adult is present
    if search_in.num_children < 0 or search_in.num_children is None:
        search_in.num_children = 0

def verify_trip_hash(booking_request: TripBookRequest):
    if not hasattr(booking_request, "option"):
        raise CabboException(
            "Invalid booking request, option is required", status_code=400
        )

    if not booking_request.option or not hasattr(booking_request.option, "hash"):
        raise CabboException(
            "Invalid booking request, option hash is required", status_code=400
        )
    if not booking_request.preferences:
        raise CabboException(
            "Invalid booking request, preferences are required", status_code=400
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
            "Invalid booking request, option hash is not valid", status_code=400
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
        print(f"Temporary trip details deleted for requestor: {requestor}")
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Failed to delete temporary trip details: {str(e)}", status_code=500
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
        date_time=booking_request.preferences.start_date
    )

    validated_end_date = None
    if booking_request.preferences.end_date:
        validated_end_date = validate_date_time(
            date_time=booking_request.preferences.end_date
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
        is_round_trip=booking_request.metadata.is_round_trip if hasattr(booking_request.metadata, "is_round_trip") else False,
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
        included_kms= booking_request.metadata.included_kms if hasattr(booking_request.metadata, "included_kms") else None,
        num_adults=booking_request.preferences.num_adults,
        num_children=booking_request.preferences.num_children,
        num_passengers=booking_request.preferences.num_adults
        + booking_request.preferences.num_children,
        num_large_suitcases=booking_request.preferences.num_large_suitcases,
        num_carryons=booking_request.preferences.num_carryons,
        num_backpacks=booking_request.preferences.num_backpacks,
        num_other_bags=booking_request.preferences.num_other_bags,
        num_luggages=_get_total_num_luggages(booking_request=booking_request),
        preferred_car_type=booking_request.preferences.preferred_car_type,
        preferred_fuel_type=booking_request.preferences.preferred_fuel_type,
        in_car_amenities=(
            booking_request.metadata.in_car_amenities.model_dump()
            if  booking_request.metadata.in_car_amenities
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
            if booking_request.preferences.flight_number
            else None
        ),
        terminal_number=(
            booking_request.preferences.terminal_number
            if booking_request.preferences.terminal_number
            else None
        ),
        toll_road_preferred=(
            booking_request.preferences.toll_road_preferred
            if booking_request.preferences.toll_road_preferred
            else False
        ),
        placard_required=(
            booking_request.preferences.placard_required
            if booking_request.preferences.placard_required
            else False
        ),
        placard_name=(
            booking_request.preferences.placard_name
            if booking_request.preferences.placard_name
            else None
        ),
        estimated_km=(
            booking_request.metadata.estimated_km
            if booking_request.metadata.estimated_km
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
    )
    try:
        db.add(temp_trip)
        db.commit()
        db.refresh(temp_trip)
        print(f"Temporary trip created for requestor: {requestor}")
        return temp_trip
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Failed to create temporary trip: {str(e)}", status_code=500
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