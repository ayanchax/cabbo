# List unique non-flagged reviews of a driver given by various customers.

from fastapi import APIRouter, Depends, Query
from core.security import validate_customer_token
from db.database import a_yield_mysql_session
from models.common import FlagsEnum
from models.customer.customer_orm import Customer
from models.driver.driver_schema import TripRatingResponseSchema
from services.trip_review_service import (
    get_average_rating_by_driver_id,
    fetch_trip_review,
    fetch_trip_review,
    list_reviews_by_driver_id,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# List unique non-flagged reviews of a driver given by various customers.
@router.get(
    "/driver/{driver_id}/ratings", response_model=list[TripRatingResponseSchema]
)
async def list_unique_reviews_of_driver(
    driver_id: str,
    flag: FlagsEnum = Query(
        FlagsEnum.none,
        description="Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews.",
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    """List unique non-flagged reviews of a driver given by various customers."""
    return await list_reviews_by_driver_id(driver_id=driver_id, flag=flag, db=db)


# See avg rating of a driver
@router.get("/driver/{driver_id}/average-rating", response_model=float)
async def get_average_rating_of_driver(
    driver_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    """Get the average rating of a driver."""
    return await get_average_rating_by_driver_id(driver_id=driver_id, db=db)


