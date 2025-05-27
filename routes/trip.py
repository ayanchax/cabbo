from fastapi import APIRouter, Depends
from core.security import validate_customer_token
from db.database import get_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_schema import (
    TripSearchRequest,
    TripSearchResponse,
)
from services.pricing_service import get_trip_search_options
from sqlalchemy.orm import Session

router = APIRouter(prefix="/trip", tags=["Trip"])


@router.post("/search", response_model=TripSearchResponse)
def search_trip(
    search_in: TripSearchRequest,
    db: Session = Depends(get_mysql_session),
    # current_customer: Customer = Depends(validate_customer_token),
):
    """
    Returns a list of top K trip options (cab/fuel/price) based on user preferences and current pricing logic.
    No DB writes. Used for search/quote workflow.
    """
    options = get_trip_search_options(search_in=search_in, db=db)
    return TripSearchResponse(options=options)
