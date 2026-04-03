from fastapi import APIRouter, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.policies.cancelation_schema import CancelationSchema
from models.user.user_orm import User
from services.cancelation_service import (
    fetch_all_cancelled_trips,
    get_cancellation_by_trip_id,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get("/", response_model=list[CancelationSchema])
async def list_all_trip_cancellations(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all trip cancellations."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip cancellations.", status_code=403
        )
    cancellations = await fetch_all_cancelled_trips(db=db)
    return cancellations


@router.get("/{trip_id}", response_model=CancelationSchema)
async def get_trip_cancellation_by_id(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get trip cancellation details by trip ID."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip cancellations.", status_code=403
        )
    cancellation = await get_cancellation_by_trip_id(trip_id=trip_id, db=db)
    if not cancellation:
        raise CabboException(
            "Cancellation not found for the specified ID.", status_code=404
        )
    return cancellation
