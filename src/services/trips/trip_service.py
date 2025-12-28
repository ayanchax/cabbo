from datetime import datetime, timedelta
import json
from typing import List, Union
from core.constants import APP_NAME
from core.exceptions import CabboException
from core.security import RoleEnum, generate_hash, verify_hash
from core.store import ConfigStore
from models.geography.region_orm import RegionModel
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
    AmenitiesSchema,
    TripBookRequest,
    TripDetails,
    TripSearchOption,
    TripSearchRequest,
    TripTypeSchema,
)
from sqlalchemy.orm import Session

from services.passenger_service import (
    get_passenger_id_from_preferences,
    populate_passenger_details,
    validate_passenger_id,
)
from services.pricing_service import (
    get_driver_allowance,
    get_parking_estimate,
    get_tolls_estimate,
)
from services.validation_service import validate_serviceable_area, validate_trip_type
from utils.utility import remove_none_recursive, validate_date_time

TRIP_MESSAGES = {
    TripStatusEnum.created.value: {
        "messages": {
            "status": TripStatusEnum.created,
            "status_text": "Your trip has been created!",
            "next_steps": [
                {
                    "id": "COMPLETE_ADVANCE_PAYMENT",
                    "step": "Complete Advance Payment",
                    "instruction": "Please complete the advance payment to confirm your trip.",
                    "reason": "This advance payment is our platform/convenience fee that helps us guarantee your trip.",
                },
                {
                    "id": "AWAIT_CONFIRMATION",
                    "step": "Await Confirmation",
                    "instruction": "You will receive a confirmation once the payment is successful.",
                },
            ],
        }
    },
    TripStatusEnum.confirmed.value: {
        "messages": {
            "status": TripStatusEnum.confirmed,
            "status_text": "Your booking has been confirmed!",
            "next_steps": [
                {
                    "id": "AWAIT_TRIP_DETAILS",
                    "step": "Await trip details",
                    "instruction": "You will receive the trip and driver details shortly.",
                },
                {
                    "id": "PAY_REMAINING_FARE",
                    "step": "Pay remaining fare after trip completion",
                    "instruction": "You will receive an invoice after your trip ends, and you should pay the rest of your fare only through the app or provided payment link in the invoice.",
                },
            ],
            "advisory": [
                {
                    "id": "DO_NOT_PAY_FOR_DRIVER_ACCOMMODATION",
                    "instruction": "You are not required or liable to arrange or pay for any driver accommodation.",
                    "additional_info": f"If you are willing to provide driver accommodation during the trip, please do so at your own discretion and {APP_NAME.capitalize()} will not be responsible for any such arrangements.",
                },
                {
                    "id": "DO_NOT_PAY_FOR_DRIVER_FOOD",
                    "instruction": "You are not required or liable to arrange or pay for any driver food or meals.",
                    "additional_info": f"If you are willing to provide driver food or meals during the trip, please do so at your own discretion and {APP_NAME.capitalize()} will not be responsible for any such arrangements.",
                },
                {
                    "id": "DO_NOT_PAY_TO_DRIVER",
                    "instruction": "Please do not make any trip related payments to the driver directly.",
                    "additional_info": "All trip related payments should be made through the app for your safety.",
                },
                {
                    "id": "DO_NOT_ENTERTAIN_PAYMENT_REQUESTS_FROM_DRIVER",
                    "instruction": "Please do not entertain any kind of payment requests from the driver.",
                    "additional_info": "All payment requests should be directed through the app for your safety. If the driver insists, please report it to our support team.",
                },
                {
                    "id": "OPTIONAL_TIPPING",
                    "instruction": "You are free to tip your driver directly in cash/UPI, at your own discretion.",
                    "additional_info": "Tipping is not mandatory but greatly appreciated.",
                },
                {
                    "id": "CONTACT_SUPPORT_GENERAL",
                    "instruction": f"If you face any issues or have concerns during your trip, please contact {APP_NAME.capitalize()} support immediately.",
                    "additional_info": "Your comfort and safety are our priority. Our support team is always here to help you.",
                },
            ],
        }
    },
}

COMMON_INCLUSIONS = [
    "Base fare",
    "Premium AC cab with professional driver",
    "Doorstep pickup and drop",
    "Platform/Convenience fee",
    "Well-maintained and sanitized vehicle",
    "24/7 customer support",
]

COMMON_EXCLUSIONS = [
    "Personal expenses",
    "Self sponsored driver meals",
    "Tolls(if applicable)",
    "Extra parking(if any)",
]

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


def get_all_trip_types(db: Session) -> List[TripTypeSchema]:
    """
    Retrieves all trips from the database.
    Returns:
        List[TripTypeSchema]: A list of all trip type master records.
    """

    try:
        trip_types = db.query(TripTypeMaster).all()
        trip_type_schemas = [
            TripTypeSchema.model_validate(trip_type) for trip_type in trip_types
        ]
        return trip_type_schemas
    except Exception as e:
        return []


def create_trip_types(trip_types: list, db: Session):
    trip_type_master_objs = [
        TripTypeMaster(
            trip_type=entry["trip_type"],
            display_name=entry["display_name"],
            description=entry["description"],
            created_by=RoleEnum.system,
        )
        for entry in trip_types
    ]
    db.add_all(trip_type_master_objs)
    db.commit()


def get_trip_package_configuration_list_by_region_code(
    region_code: str, db: Session
) -> List[TripPackageConfigSchema]:
    trip_package_config = (
        db.query(TripPackageConfig)
        .join(RegionModel, TripPackageConfig.region_id == RegionModel.id)
        .filter(
            RegionModel.region_code == region_code,
        )
        .all()
    )
    if not trip_package_config:
        return []
    return [
        TripPackageConfigSchema.model_validate(config) for config in trip_package_config
    ]


def get_trip_type_id_by_trip_type(
    trip_type: TripTypeEnum, db: Session, include_id_only=True
) -> Union[str, TripTypeSchema]:
    """
    Retrieves the trip type ID from the database based on the provided trip type.
    Args:
        trip_type (TripTypeEnum): The trip type for which to retrieve the ID.
        db (Session): The database session for ORM operations.
    Returns:
        Union[str, TripTypeSchema]: The trip type object if include_id_only is False.
    Raises:
        CabboException: If the trip type is not found in the database.
    """
    trip_type_obj = (
        db.query(TripTypeMaster).filter(TripTypeMaster.trip_type == trip_type).first()
    )
    if not trip_type_obj:
        raise CabboException(f"Trip type {trip_type} not found", status_code=404)
    return (
        trip_type_obj.id
        if include_id_only
        else TripTypeSchema.model_validate(trip_type_obj)
    )


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


def get_default_trip_amenities():
    return AmenitiesSchema(
        water_bottle=True,
        tissues=True,
        ac=True,
        music_system=True,
    )


def generate_trip_field_dictionary(
    search_in: TripSearchRequest,
    car_type: str,
    fuel_type: str,
    option: TripSearchOption,
):
    """Generates a dictionary of trip fields for the booking option and preferences.
    This method creates a dictionary representation of the trip option and preferences
    for use in generating a hash to verify the integrity of the booking data.

    Args:
        search_in (TripSearchRequest): The trip search request containing user preferences.
        car_type (str): The car type selected for the trip.
        fuel_type (str): The fuel type selected for the trip.
        option (TripSearchOption): The trip search option containing pricing and breakdown details.

    Returns:
        tuple: A tuple containing two dictionaries:
            - option_dict: Dictionary of trip option fields.
            - preference_dict: Dictionary of user preferences for the trip.
    """
    option_dict = {
        "car_type": car_type,  # Use display name from schema
        "fuel_type": fuel_type,  # Use display name from schema
        "total_price": option.total_price,
    }
    preference_dict = {
        "trip_type": search_in.trip_type,
        "origin": search_in.origin.model_dump() if search_in.origin else None,
        "start_date": search_in.start_date,
    }
    passenger_id = get_passenger_id_from_preferences(preferences=search_in)
    if passenger_id:
        preference_dict["passenger_id"] = passenger_id

    if search_in.trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        preference_dict["destination"] = (
            search_in.destination.model_dump() if search_in.destination else None
        )

    elif search_in.trip_type == TripTypeEnum.local:
        option_dict["package"] = option.package
        option_dict["package_short_label"] = option.package_short_label
        option_dict["included_hours"] = option.included_hours
        option_dict["included_km"] = option.included_km
    elif search_in.trip_type == TripTypeEnum.outstation:
        preference_dict["destination"] = (
            search_in.destination.model_dump() if search_in.destination else None
        )
        preference_dict["start_date"] = search_in.end_date
    else:
        # For other trip types, we can set additional fields if needed
        pass

    return option_dict, preference_dict


def generate_trip_hash(option: dict, preferences: dict) -> str:
    """
    Generate a hash for the trip booking option and preferences.
    This is used to verify the integrity of the booking data.
    """
    payload = json.dumps({"option": option, "preferences": preferences}, sort_keys=True)
    return generate_hash(payload)


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


def derive_trip_sort_priority(search_in: TripSearchRequest, option: TripSearchOption):
    # 1. User preferred car type/fuel type always first
    pref_score = 0
    if search_in.preferred_car_type and option.car_type == search_in.preferred_car_type:
        pref_score -= 1000  # Strong preference
    if (
        search_in.preferred_fuel_type
        and option.fuel_type == search_in.preferred_fuel_type
    ):
        pref_score -= 500
    # 2. Passenger count logic
    total_pax = search_in.num_adults + search_in.num_children
    if total_pax > 4:  # More than 4 passengers, prefer larger vehicles
        if option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
            pref_score -= 200
    elif total_pax <= 4:  # 4 or fewer passengers, prefer smaller vehicles
        if option.car_type in [CarTypeEnum.sedan, CarTypeEnum.sedan_plus]:
            pref_score -= 100
    if total_pax <= 3:  #
        if option.car_type == CarTypeEnum.hatchback:
            pref_score -= 50
    # 3. Luggage logic (fine-grained)
    num_large_suitcases = search_in.num_large_suitcases or 0
    num_carryons = search_in.num_carryons or 0
    num_backpacks = search_in.num_backpacks or 0
    num_other_bags = search_in.num_other_bags or 0
    # Strongly prefer SUV/SUV+ only if large suitcases/trolley bags are 3 or more
    if num_large_suitcases >= 3:
        if option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
            pref_score -= 300  # Strong preference for SUV/SUV+
        else:
            pref_score += 200  # Penalize smaller cars
    # Strongly prefer sedan/premium sedan if large suitcases/trolley bags are exactly 2
    elif num_large_suitcases == 2:
        if option.car_type in [CarTypeEnum.sedan, CarTypeEnum.sedan_plus]:
            pref_score -= 200  # Strong preference for sedan/sedan+
        elif option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
            pref_score += 50  # Slightly penalize SUV/SUV+ (overkill for 2 bags)
        elif option.car_type == CarTypeEnum.hatchback:
            pref_score += 200  # Penalize hatchback

    # Moderate preference for SUV/SUV+ for other bag types
    elif num_carryons > 2 or num_backpacks > 1 or num_other_bags > 1:
        if option.car_type in [CarTypeEnum.suv, CarTypeEnum.suv_plus]:
            pref_score -= 150
        else:
            pref_score += 100
    elif num_carryons <= 2 or num_backpacks == 1 or num_other_bags == 1:
        if option.car_type in [CarTypeEnum.sedan, CarTypeEnum.sedan_plus]:
            pref_score -= 100
        elif option.car_type == CarTypeEnum.hatchback:
            pref_score += 100
    # 4. Price as a tiebreaker
    return (pref_score, option.total_price)


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
        is_round_trip=booking_request.metadata.is_round_trip or False,
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
            if booking_request.metadata.total_trip_days
            else None
        ),
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
        base_fare=booking_request.option.price_breakdown.base_fare,
        driver_allowance=(
            get_driver_allowance(option=booking_request.option)
            if booking_request.preferences.trip_type
            in [TripTypeEnum.outstation, TripTypeEnum.local]
            else 0.0
        ),
        tolls_estimate=get_tolls_estimate(booking_request=booking_request),
        parking_estimate=get_parking_estimate(booking_request=booking_request),
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