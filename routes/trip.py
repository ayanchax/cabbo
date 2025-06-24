from fastapi import APIRouter, Depends
from core.security import validate_customer_token
from db.database import get_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_schema import (
    TripBookRequest,
    TripSearchRequest,
    TripSearchResponse,
)
from services.trip_service import get_trip_search_options
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
    No DB writes. Used for search workflow.
    """
    return get_trip_search_options(search_in=search_in, db=db)


@router.post("/book")
def book_trip(
    trip_in: TripBookRequest,
    db: Session = Depends(get_mysql_session),
    # current_customer: Customer = Depends(validate_customer_token),
):
    """
    Books/confirms a trip directly from the search options. Creates a trip with status = 'created'.
    Returns trip_id and summary. (Happy path, no negotiation.)
    """
    # TODO: Implement trip creation logic, set status = 'created', persist to DB, return trip_id and summary
    pass


@router.post("/quote")
def quote_trip(
    trip_in: TripBookRequest,
    db: Session = Depends(get_mysql_session),
    # current_customer: Customer = Depends(validate_customer_token),
):
    """
    Submits a quote/counter-offer for a trip. Creates a trip with status = 'quoted' and stores quoted price.
    Returns trip_id and summary. (Negotiation flow.)
    """
    # TODO: Implement trip creation logic, set status = 'quoted', store quoted price, persist to DB, return trip_id and summary
    pass
