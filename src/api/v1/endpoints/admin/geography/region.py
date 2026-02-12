from fastapi import APIRouter
from fastapi.params import Depends
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.geography.region_schema import RegionSchema, RegionUpdate
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession

from services.geography_service import (
    async_activate_region,
    async_add_region,
    async_delete_region,
    async_get_all_regions,
    async_update_region,
)


router = APIRouter()


# Region/City Management
@router.post(
    "/add",
    response_model=RegionSchema,
)
async def add_region(
    region: RegionSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new region/city to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to add regions.", status_code=403
        )
    return await async_add_region(payload=region, db=db, created_by=current_user_role)


@router.get(
    "/list",
    response_model=list[RegionSchema],
)
async def list_regions(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all regions/cities in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view regions.", status_code=403
        )

    return await async_get_all_regions(db=db)


@router.put(
    "/{region_id}",
    response_model=RegionSchema,
)
async def update_region(
    region: RegionUpdate,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update an existing region/city's configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update regions.", status_code=403
        )
    result, error = await async_update_region(payload=region, db=db)
    if not result:
        raise CabboException(
            status_code=500, message=error or "Failed to update region"
        )
    return result

#Activate a region
@router.patch("/{region_id}/activate")
async def activate_region(region_id:str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Activate a region/city in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to activate regions.", status_code=403
        )
    result, error = await async_activate_region(region_id=region_id, db=db)
    if not result:
        raise CabboException(status_code=500, message=error or "Failed to activate region")
    return {"detail": f"Region {region_id} activated successfully."}


@router.delete(
    "/{region_id}",
)
async def delete_region(
    region_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Delete a region/city from the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete regions.", status_code=403
        )
    is_deleted, error = await async_delete_region(region_id=region_id, db=db)
    if not is_deleted:
        raise CabboException(error or "Failed to delete region", status_code=400)
    return {"detail": f"Region {region_id} deleted successfully."}
