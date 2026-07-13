
from fastapi import APIRouter, Depends

from customer_api.src.core.exceptions import GENERIC_EXCEPTION, UNAUTHORIZED, CabboException
from customer_api.src.core.security import RoleEnum, validate_user_token
from customer_api.src.db.database import a_yield_mysql_session
from customer_api.src.models.policies.dispute_schema import DisputeSchema, DisputeUpdateSchema
from customer_api.src.models.user.user_orm import User
from customer_api.src.services.dispute_service import get_dispute_by_trip_id, update_dispute_by_trip_id
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

#Get endpoint for dispute of a trip
@router.get("/{trip_id}", response_model=DisputeSchema)
async def get_trip_dispute(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get dispute details for a trip."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip disputes.", status_code=403, error_code=UNAUTHORIZED
        )
    dispute = await get_dispute_by_trip_id(trip_id=trip_id, db=db)
    if not dispute:
        raise CabboException("Dispute not found for the specified trip.", status_code=404, error_code=GENERIC_EXCEPTION)
    return dispute

#Patch endpoint for updating dispute details for a trip (admin support agent can update the dispute details based on the investigation and resolution process)
#PATCH endpoint for dispute of a trip updating status, details and comments - by super admin, customer_admin
@router.patch("/{trip_id}", response_model=DisputeSchema)
async def update_trip_dispute(
    trip_id: str,
    payload: DisputeUpdateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update dispute details for a trip."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to update trip disputes.", status_code=403, error_code=UNAUTHORIZED
        )
    return await update_dispute_by_trip_id(trip_id=trip_id, payload=payload, db=db, requestor=current_user.id)
    