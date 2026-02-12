from fastapi import APIRouter
from fastapi.params import Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.cab.cab_schema import FuelTypeSchema
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession

from services.fuel_service import (
    async_activate_fuel_type,
    async_add_fuel_type,
    async_delete_fuel_type,
    async_get_all_fuel_types,
    async_get_fuel_type_by_id,
    async_update_fuel_type,
)

router = APIRouter()


# ====== Fuel Configuration Endpoints ================
# Add fuel type
@router.post("/type", response_model=FuelTypeSchema)
async def add_fuel_type(
    fuel_type: FuelTypeSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new fuel type to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to add fuel types.", status_code=403
        )
    result = await async_add_fuel_type(
        fuel_type=fuel_type, db=db, created_by=current_user_role
    )
    if not result:
        raise CabboException(status_code=500, message="Failed to add new fuel type")
    return result


# List fuel types
@router.get("/types", response_model=list[FuelTypeSchema])
async def list_fuel_types(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all fuel types in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view fuel types.", status_code=403
        )
    return await async_get_all_fuel_types(db=db)


# Update fuel type
@router.put("/type/{fuel_type_id}", response_model=FuelTypeSchema)
async def update_fuel_type(fuel_type: FuelTypeSchema, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Update an existing fuel type's configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to update fuel types.", status_code=403
        )
    result = await async_update_fuel_type(fuel_type_data=fuel_type, db=db)
    if not result:
        raise CabboException(status_code=500, message="Failed to update fuel type")
    return result

#Get fuel type by id
@router.get("/type/{fuel_type_id}", response_model=FuelTypeSchema)
async def get_fuel_type(fuel_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Retrieve a fuel type by its ID."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view fuel types.", status_code=403
        )
    fuel_type = await async_get_fuel_type_by_id(fuel_type_id=fuel_type_id, db=db)
    if not fuel_type:
        raise CabboException(status_code=404, message="Fuel type not found")
    return fuel_type

@router.patch("/type/{fuel_type_id}/activate")
async def activate_fuel_type(fuel_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)): 
    """Activate a fuel type in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
            raise CabboException( "You do not have permission to activate fuel types.", status_code=403 ) 
    is_activated, error = await async_activate_fuel_type(fuel_type_id=fuel_type_id, db=db) 
    if not is_activated: 
        raise CabboException(status_code=500, message=error or "Failed to activate fuel type") 
    return {"detail": f"Fuel type {fuel_type_id} activated successfully."}



# Delete fuel type
@router.delete("/type/{fuel_type_id}")
async def delete_fuel_type(
    fuel_type_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Delete a fuel type from the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to delete fuel types.", status_code=403
        )
    is_deleted, error = await async_delete_fuel_type(fuel_type_id=fuel_type_id, db=db)

    if not is_deleted:
        raise CabboException(
            status_code=500, message=error or "Failed to delete fuel type"
        )

    return {"detail": f"Fuel type {fuel_type_id} deleted successfully."}
