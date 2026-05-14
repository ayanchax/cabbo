from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.config import settings
from db.database import yield_mysql_session
from models.trip.trip_schema import TripClassificationRequest
from services.trip_type_service import classify_trip_type
from services.validation_service import validate_initial_serviceable_area
from utils.utility import remove_none_recursive

router = APIRouter()


@router.post("/classify")
def classify(
    payload: TripClassificationRequest,
    db: Session = Depends(yield_mysql_session),
):
    config_store = settings.get_config_store(db)
    result = classify_trip_type(
        pickup=payload.pickup,
        dropoff=payload.dropoff,
        config_store=config_store,
    )
    payload.trip_type = result.trip_type

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
