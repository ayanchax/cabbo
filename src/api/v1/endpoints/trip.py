from fastapi import APIRouter
from models.trip.trip_schema import TripClassificationRequest
from services.trip_type_service import classify_trip_type
router = APIRouter()


@router.post("/classify")
def classify(
    payload:TripClassificationRequest
):
     return classify_trip_type(
         pickup=payload.pickup,
         dropoff=payload.dropoff,
     )
     