# Trip type master endpoints for admin configuration - add, list, update and delete trip types in the system, can be operated only by super admin

from fastapi import APIRouter, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from models.trip.trip_schema import TripTypeSchema, TripTypeUpdateSchema
from models.user.user_orm import User
from db.database import a_yield_mysql_session
from sqlalchemy.ext.asyncio import AsyncSession

from services.trip_type_service import (
    async_activate_trip_type,
    async_add_trip_type,
    async_delete_trip_type,
    async_get_all_trip_types,
    async_get_trip_type_by_id,
    async_update_trip_type,
)


router = APIRouter()


# Add a new trip type
@router.post("/add", response_model=TripTypeSchema)
async def add_trip_type(
    payload: TripTypeSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new trip type to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to add trip types.", status_code=403
        )
    new_trip_type, error = await async_add_trip_type(
        trip_type_data=payload, db=db, created_by=current_user_role
    )
    if error:
        raise CabboException(error, status_code=400)
    if not new_trip_type:
        raise CabboException("Failed to add new trip type", status_code=500)
    return TripTypeSchema.model_validate(new_trip_type)


# List all trip types
@router.get("/list", response_model=list[TripTypeSchema])
async def list_trip_types(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all trip types in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to list trip types.", status_code=403
        )
    return await async_get_all_trip_types(db=db)


# Get a trip type by id
@router.get("/{trip_type_id}", response_model=TripTypeSchema)
async def get_trip_type_by_id(
    trip_type_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Retrieve a trip type by its ID."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view trip types.", status_code=403
        )
    trip_type = await async_get_trip_type_by_id(trip_type_id=trip_type_id, db=db)
    if not trip_type:
        raise CabboException(status_code=404, message="Trip type not found")
    return trip_type


# Update a trip type
@router.put("/{trip_type_id}", response_model=TripTypeSchema)
async def update_trip_type(
    trip_type_id: str,
    payload: TripTypeUpdateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update trip types.", status_code=403
        )
    payload.id = trip_type_id
    updated_trip_type, error = await async_update_trip_type(
        trip_type_data=payload, db=db
    )
    if error:
        raise CabboException(error, status_code=400)
    if not updated_trip_type:
        raise CabboException("Failed to update trip type", status_code=500)
    return updated_trip_type


# Delete a trip type
@router.delete("/{trip_type_id}")
async def delete_trip_type(
    trip_type_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete trip types.", status_code=403
        )
    success, error = await async_delete_trip_type(trip_type_id=trip_type_id, db=db)
    if error:
        raise CabboException(error, status_code=400)
    if not success:
        raise CabboException("Failed to delete trip type", status_code=500)
    return {"message": "Trip type deleted successfully"}


# Activate a trip type
@router.post("/{trip_type_id}/activate")
async def activate_trip_type(
    trip_type_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to activate trip types.", status_code=403
        )
    success, error = await async_activate_trip_type(trip_type_id=trip_type_id, db=db)
    if error:
        raise CabboException(error, status_code=400)
    if not success:
        raise CabboException("Failed to activate trip type", status_code=500)
    return {"message": "Trip type activated successfully"}
