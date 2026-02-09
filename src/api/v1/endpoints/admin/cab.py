from fastapi import APIRouter
from fastapi.params import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session, yield_mysql_session
from models.cab.cab_schema import CabTypeSchema, CabTypeUpdateSchema
from models.user.user_orm import User
from services.cab_service import add_new_cab_type, async_delete_cab_type, async_get_all_cabs, async_update_cab_type


router = APIRouter()

# ====== Cab Configuration Endpoints ================

# Add cab type 
@router.post("/type", response_model=CabTypeSchema)
async def add_cab_type(cab_type: CabTypeSchema, db: AsyncSession = Depends(a_yield_mysql_session),current_user: User = Depends(validate_user_token),):
    """Add a new cab type to the system configuration."""
    current_user_role = current_user.role
    
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to add cab types.", status_code=403
        )
    
    result = await add_new_cab_type(cab_type=cab_type, db=db, created_by=current_user_role)
    if not result:
        raise CabboException(status_code=500, message="Failed to add new cab type")
    return result

# List cab types
@router.get("/types", response_model=list[CabTypeSchema])
async def list_cab_types(db:AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """List all cab types in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view cab types.", status_code=403
        )
    return await async_get_all_cabs(db=db)

# Update cab type
@router.put("/type", response_model=CabTypeSchema)
async def update_cab_type(cab_type: CabTypeUpdateSchema, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Update an existing cab type's configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to update cab types.", status_code=403
        )
    # Implementation to update cab type goes here
    result = await async_update_cab_type(cab_type_data=cab_type, db=db)
    if not result:
        raise CabboException(status_code=500, message="Failed to update cab type")
    return result
    

# Delete cab type
@router.delete("/type/{cab_type_id}")
async def delete_cab_type(cab_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Delete a cab type from the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to delete cab types.", status_code=403
        )
    success, error_message = await async_delete_cab_type(cab_type_id=cab_type_id, db=db)
    if not success:
        raise CabboException(status_code=400, message=error_message or "Failed to delete cab type")
    
    return {"detail": f"Cab type {cab_type_id} deleted successfully."}
    

