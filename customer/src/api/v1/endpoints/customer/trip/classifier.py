from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from customer_api.src.core.config import settings
from customer_api.src.core.security import validate_customer_token
from customer_api.src.db.database import yield_mysql_session
from customer_api.src.models.customer.customer_orm import Customer
from customer_api.src.models.trip.trip_enums import TripTypeEnum
from customer_api.src.models.trip.trip_schema import TripClassificationRequest
from customer_api.src.services.trip_type_service import classify_trip_type
from customer_api.src.services.validation_service import validate_initial_serviceable_area
from customer_api.src.utils.utility import remove_none_recursive

router = APIRouter()


@router.post("/classify")
def classify(
    payload: TripClassificationRequest,
    db: Session = Depends(yield_mysql_session),
    _: Customer = Depends(validate_customer_token),

):
    config_store = settings.get_config_store(db)
    result = classify_trip_type(
        pickup=payload.pickup,
        dropoff=payload.dropoff,
        config_store=config_store,
    )
    payload.trip_type = result.trip_type
    # Only swap pickup and dropoff if the trip is classified as non-local and one of the locations is empty while the other is not. For local trips, we allow one location to be empty without swapping, as local trips can be classified based on a single location.
    payload.swap_empty_with_non_empty = False if payload.trip_type == TripTypeEnum.local and not payload.dropoff else True # Only swap for non-local trips, as local trips can have one location and still be classified as local. For non-local trips, if one location is empty and the other is not, we can swap them to increase chances of successful classification.

    if payload.validate_serviceable_area:
        payload = validate_initial_serviceable_area(
            classification_request=payload,
            config_store=config_store,
        )

    return remove_none_recursive(
        {
            "trip_type": payload.trip_type,
            "distance_km": result.distance_km,
            "has_distance_overage": result.has_distance_overage,
            "pickup": payload.pickup.model_dump() if payload.pickup else None,
            "dropoff": payload.dropoff.model_dump() if payload.dropoff else None,
            "serviceable": payload.serviceable,
        }
    )
