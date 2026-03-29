from fastapi import APIRouter, Depends, Query
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.common import FlagsEnum
from models.trip.trip_schema import TripRatingResponseSchema
from models.user.user_orm import User
from services.trip_review_service import (
    fetch_trip_review_by_trip_id,
    fetch_trip_reviews_by_customer_id_and_driver_id,
    fetch_trip_reviews_by_driver_id,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/driver/{driver_id}", response_model=list[TripRatingResponseSchema])
async def view_trip_reviews_by_driver_id(
    driver_id: str,
    flag: FlagsEnum = Query(
        FlagsEnum.none,
        description="Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews.",
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """LIST View all trip reviews for a driver given by various customers."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_trip_reviews_by_driver_id(driver_id=driver_id, flag=flag, db=db)


# View all trip reviews by a specific customer for a driver
@router.get(
    "/driver/{driver_id}/customer/{customer_id}",
    response_model=list[TripRatingResponseSchema],
)
async def view_trip_reviews_by_customer_driver(
    driver_id: str,
    customer_id: str,
    flag: FlagsEnum = Query(
        FlagsEnum.none,
        description="Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews.",
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """LIST View trip reviews for a specific driver given by a specific customer."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_trip_reviews_by_customer_id_and_driver_id(
        driver_id=driver_id, customer_id=customer_id, flag=flag, db=db
    )


# View trip review for a specific trip
@router.get("/trip/{trip_id}", response_model=TripRatingResponseSchema)
async def view_trip_review(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Object View trip review for a specific trip for a driver."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_trip_review_by_trip_id(trip_id=trip_id, db=db)
