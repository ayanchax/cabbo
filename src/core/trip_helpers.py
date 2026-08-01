import json
from typing import List, Optional, Union
from core.exceptions import INVALID_TRIP_TYPE, TRIP_TYPE_ID_NOT_FOUND, CabboException
from core.security import RoleEnum, generate_hash
from core.trip_constants import OUTSTATION_DEFAULTS, TRIP_RESPONSE_OPTIONS
from db.database import get_mysql_local_session
from models.common import AmenitiesSchema
from models.financial.payments_schema import PaymentNotesSchema
from models.geography.region_orm import RegionModel
from models.pricing.pricing_schema import TripPackageConfigSchema
from models.trip.trip_enums import TripResponseView, TripTypeEnum
from models.trip.trip_orm import Trip, TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import  TripDetails, TripSearchOption, TripSearchRequest, TripTypeSchema
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from services.passenger_service import get_passenger_id_from_preferences
import logging
log = logging.getLogger(__name__)

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
        raise CabboException(f"Trip type {trip_type} not found", status_code=404, error_code=INVALID_TRIP_TYPE)
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
        log.error(f"Error fetching trip types: {e}")
        return []


def get_trip_package_configuration_list_by_region_code(
    region_code: str, db: Session
) -> List[TripPackageConfigSchema]:
    trip_package_config = (
        db.query(TripPackageConfig)
        .join(RegionModel, TripPackageConfig.region_id == RegionModel.id)
        .filter(
            RegionModel.region_code == region_code, TripPackageConfig.is_active == True
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
    db.flush()  # Flush to get IDs assigned

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
        option_dict["included_km"] = option.included_kms
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


def get_trip_type_by_trip_type_id(trip_type_id: str, db: Session, use_cache=True) -> TripTypeEnum:
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
    if use_cache:
        from core.config import settings
        config_store = settings.get_config_store(db)
        trip_types = config_store.trip_types
        trip_type_obj= next(trip_type for trip_type in trip_types if trip_type.id == trip_type_id)
        if not trip_type_obj:
            raise CabboException(
            f"Trip type with ID {trip_type_id} not found", status_code=404, error_code=TRIP_TYPE_ID_NOT_FOUND
        )
        return TripTypeEnum(trip_type_obj.trip_type)


    trip_type_obj = (
        db.query(TripTypeMaster).filter(TripTypeMaster.id == trip_type_id, TripTypeMaster.is_active).first()
    )
    if not trip_type_obj:
        raise CabboException(
            f"Trip type with ID {trip_type_id} not found", status_code=404, error_code=TRIP_TYPE_ID_NOT_FOUND
        )
    return TripTypeEnum(trip_type_obj.trip_type)


async def attach_relationships_to_trip(
    trip: Trip,
    db: AsyncSession,
    view: Optional[TripResponseView] = None,
):
    options = TRIP_RESPONSE_OPTIONS.get(view) if view else None

    relationship_names = []
    if trip.driver_id:
        relationship_names.append("driver")
    if trip.trip_type_id:
        relationship_names.append("trip_type_master")
    if trip.package_id:
        relationship_names.append("package")
    if trip.passenger_id:
        relationship_names.append("passenger")
    if options and options.expose_customer_details and trip.creator_id:
        relationship_names.append("customer")
    if options and options.expose_cancellation_detail:
        relationship_names.append("cancellation")
    if options and options.expose_dispute_details:
        relationship_names.append("dispute")
    if options and options.expose_trip_review:
        relationship_names.append("trip_rating")
    if options and options.expose_trip_refund:
        relationship_names.append("refund")


    for relationship_name in relationship_names:
        await db.refresh(trip, attribute_names=[relationship_name])


def attach_trip_details_to_order_notes(order: dict, trip_details: TripDetails):
    
    notes = order.get("notes", {})
    notes = PaymentNotesSchema.model_validate(notes)  # Validate the notes structure
    # Ensure that trip_details is set in notes
    if not hasattr(notes, "trip_details"):
        notes.trip_details = trip_details

    order["notes"] = notes.model_dump(
        exclude_none=True
    )  # Update the order with the notes containing trip details


def get_prior_booking_window_hours(
    trip_type: TripTypeEnum, jurisdiction_code: Optional[str]
) -> Optional[int]:
    try:
        from core.config import settings
        config_store = settings.get_config_store(get_mysql_local_session())
        if trip_type == TripTypeEnum.airport_pickup:
            if jurisdiction_code and config_store.airport_pickup.get(jurisdiction_code):
                return config_store.airport_pickup.get(
                    jurisdiction_code
                ).auxiliary_pricing.common.prior_booking_window_hours
        elif trip_type == TripTypeEnum.airport_drop:
            if jurisdiction_code and config_store.airport_drop.get(jurisdiction_code):
                return config_store.airport_drop.get(
                    jurisdiction_code
                ).auxiliary_pricing.common.prior_booking_window_hours
        elif trip_type == TripTypeEnum.outstation:
            if jurisdiction_code and config_store.outstation.get(jurisdiction_code):
                return config_store.outstation.get(
                    jurisdiction_code
                ).auxiliary_pricing.common.prior_booking_window_hours
        elif trip_type == TripTypeEnum.local:
            if jurisdiction_code and config_store.local.get(jurisdiction_code):
                return config_store.local.get(
                    jurisdiction_code
                ).auxiliary_pricing.common.prior_booking_window_hours
    except Exception as e:
        log.error(f"Error fetching prior booking window hours from config: {e}")
    return None


def get_trip_constraints_by_trip_type(trip_type: TripTypeEnum, jurisdiction_code: Optional[str], db: Session) -> dict:
    from core.config import settings
    config_store = settings.get_config_store(db)
    
    if trip_type == TripTypeEnum.outstation:
        config = config_store.outstation.get(jurisdiction_code)
        if config and config.auxiliary_pricing and config.auxiliary_pricing.common:
            return {
                "max_hops": config.auxiliary_pricing.common.max_hops_allowed or OUTSTATION_DEFAULTS.get("max_hops", 3),
                "min_trip_days": config.auxiliary_pricing.common.min_days_allowed or OUTSTATION_DEFAULTS.get("min_days_allowed", 2),
                "max_trip_days": config.auxiliary_pricing.common.max_days_allowed or OUTSTATION_DEFAULTS.get("max_days_allowed", 7),
                "round_trip_only":True
            }
    # Add more trip type specific constraints if needed
    return {}
