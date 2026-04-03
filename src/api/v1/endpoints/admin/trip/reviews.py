from fastapi import APIRouter, BackgroundTasks, Depends, Query
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.common import AppBackgroundTask, FlagsEnum
from models.trip.trip_schema import TripRatingResponseSchema
from models.user.user_orm import User
from services.orchestration_service import BackgroundTaskOrchestrator
from services.trip_review_service import (
    fetch_all_trip_reviews,
    fetch_trip_review_by_review_id,
    fetch_trip_review_by_trip_id,
    fetch_trip_reviews_by_customer_id,
    fetch_trip_reviews_by_driver_id,
    update_trip_review_flag_status,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# View trip review for a specific trip
@router.get("/trip/{trip_id}", response_model=TripRatingResponseSchema)
async def view_trip_review_by_trip_id(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Object View trip review for a specific trip for a driver."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_trip_review_by_trip_id(trip_id=trip_id, db=db)


# View trip review by review id
@router.get("/{review_id}", response_model=TripRatingResponseSchema)
async def view_trip_review_by_review_id(
    review_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Object View trip review for a specific review id."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_trip_review_by_review_id(review_id=review_id, db=db)


# View all trip reviews by various customers to various drivers.
@router.get("/", response_model=list[TripRatingResponseSchema])
async def view_all_trip_reviews(
    flag: FlagsEnum = Query(
        FlagsEnum.none,
        description="Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews.",
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """LIST View all trip reviews by various customers to various drivers."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_all_trip_reviews(flag=flag, db=db)


# View all trip reviews given by a specific customer
@router.get("/customer/{customer_id}", response_model=list[TripRatingResponseSchema])
async def view_trip_reviews_by_customer_id(
    customer_id: str,
    flag: FlagsEnum = Query(
        FlagsEnum.none,
        description="Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews.",
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """LIST View all trip reviews for a specific customer given by various drivers."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_trip_reviews_by_customer_id(
        customer_id=customer_id, flag=flag, db=db
    )


# View all trip reviews for a specific driver given by various customers
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
    """LIST View all trip reviews for a specific driver given by various customers."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view trip reviews.", status_code=403
        )
    return await fetch_trip_reviews_by_driver_id(driver_id=driver_id, flag=flag, db=db)


# Update trip review flag status by review_id.
@router.put("/{review_id}/flag")
async def update_trip_review_flag_status_by_review_id(
    background_tasks: BackgroundTasks,
    review_id: str,
    flagged: bool = Query(
        False,
        description="Flag status to be updated for the trip review. Use true to flag the review as inappropriate or fake, and false to unflag the review.",
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update the flagged status of a trip review by review id. This can be used by admins to flag a review as inappropriate or fake if it violates community guidelines or is suspected to be fraudulent, and unflag a review if it was flagged by mistake or if the issue with the review has been resolved."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to update trip reviews.", status_code=403
        )
    success, background_task_or_message = await update_trip_review_flag_status(
        review_id=review_id, is_flagged=flagged, db=db
    )
    if not success and isinstance(background_task_or_message, str):
        raise CabboException(status_code=400, message=background_task_or_message)

    if isinstance(background_task_or_message, AppBackgroundTask):
        background_task = background_task_or_message
        orchestrator = BackgroundTaskOrchestrator(background_tasks)
        orchestrator.add_task(
            background_task.fn,
            task_name=f"BackgroundTaskUpdateDriverAvgRating",
            **background_task.kwargs,
        )
    return {"message": "Trip review flag status updated successfully."}
