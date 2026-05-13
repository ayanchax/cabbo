from fastapi import APIRouter, Query
from models.trip.trip_schema import TripClassificationRequest
from services.trip_type_service import classify_trip_type
router = APIRouter()


@router.post("/classify")
def classify(
    payload:TripClassificationRequest,
):
     trip_type= classify_trip_type(
         pickup=payload.pickup,
         dropoff=payload.dropoff,
     )
     if payload.validate_serviceable_area:
            pass
     return trip_type
     