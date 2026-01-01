import json
from typing import List, Union
from core.exceptions import CabboException
from core.security import RoleEnum, generate_hash
from models.geography.region_orm import RegionModel
from models.pricing.pricing_schema import TripPackageConfigSchema
from models.trip.trip_enums import CarTypeEnum, TripTypeEnum
from models.trip.trip_orm import TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import AmenitiesSchema, TripSearchOption, TripSearchRequest, TripTypeSchema
from sqlalchemy.orm import Session

from services.passenger_service import get_passenger_id_from_preferences


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
        "origin": search_in.origin.model_dump(exclude_none=True, exclude_unset=True) if search_in.origin else None,
        "start_date": search_in.start_date,
    }
    passenger_id = get_passenger_id_from_preferences(preferences=search_in)
    if passenger_id:
        preference_dict["passenger_id"] = passenger_id

    if search_in.trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        preference_dict["destination"] = (
            search_in.destination.model_dump(exclude_none=True, exclude_unset=True) if search_in.destination else None
        )

    elif search_in.trip_type == TripTypeEnum.local:
        option_dict["package"] = option.package
        option_dict["package_short_label"] = option.package_short_label
        option_dict["included_hours"] = option.included_hours
        option_dict["included_km"] = option.included_km
    elif search_in.trip_type == TripTypeEnum.outstation:
        preference_dict["destination"] = (
            search_in.destination.model_dump(exclude_none=True, exclude_unset=True) if search_in.destination else None
        )
        if search_in.hops:
            preference_dict["hops"] = [
                hop.model_dump(exclude_none=True, exclude_unset=True) for hop in search_in.hops
            ] if search_in.hops else []

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


def get_default_trip_amenities():
    return AmenitiesSchema(
        water_bottle=True,
        tissues=True,
        ac=True,
        music_system=True,
    )



