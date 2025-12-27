from typing import List, Union
from core.constants import APP_NAME
from core.exceptions import CabboException
from core.security import RoleEnum
from models.geography.region_orm import RegionModel
from models.pricing.pricing_schema import (
    TripPackageConfigSchema,
)
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripStatusEnum, TripTypeEnum
from models.trip.trip_orm import TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import (
    TripSearchRequest,
    TripTypeSchema,
)
from sqlalchemy.orm import Session

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


def get_trip_package_configuration_by_region_code(
    region_code: str, db: Session
) -> TripPackageConfigSchema:
    trip_package_config = (
        db.query(TripPackageConfig)
        .join(RegionModel, TripPackageConfig.region_id == RegionModel.id)
        .filter(
            RegionModel.region_code == region_code,
        )
        .first()
    )
    if not trip_package_config:
        return None
    return TripPackageConfigSchema.model_validate(trip_package_config)


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


def set_default_preferences(search_in: TripSearchRequest):
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

