# Local trip package management endpoints for admin users - add, list, update and delete local trip packages in the system by region code, can be operated only by admin users like super_admin and regional_admin

from fastapi import APIRouter, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from models.trip.trip_schema import (
    TripPackageSchema,
    TripPackageUpdateSchema,
)
from models.user.user_orm import User
from db.database import a_yield_mysql_session
from sqlalchemy.ext.asyncio import AsyncSession

from services.trip_package_service import (
    activate_trip_package_config_by_id,
    create_trip_package_config,
    delete_trip_package_config_by_id,
    get_trip_package_config_by_id,
    list_trip_package_configs,
    list_trip_package_configs_by_region_code,
    update_trip_package_config,
)


router = APIRouter()


# Add a new local trip package
@router.post("/add", response_model=TripPackageSchema)
async def add_local_trip_package(
    payload: TripPackageSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new local trip package to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to add local trip packages.", status_code=403
        )
    return await create_trip_package_config(payload, db, current_user.id)


# List all local trip packages
@router.get("/list", response_model=list[TripPackageSchema])
async def list_local_trip_packages(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all local trip packages in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to list local trip packages.", status_code=403
        )
    return await list_trip_package_configs(db)


# list all local trip packages by region code
@router.get("/list/{region_code}", response_model=list[TripPackageSchema])
async def list_local_trip_packages_by_region_code(
    region_code: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all local trip packages in the system configuration for a specific region code."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to list local trip packages by region code.",
            status_code=403,
        )
    return await list_trip_package_configs_by_region_code(region_code, db)


# Update a local trip package by id
@router.put("/", response_model=TripPackageSchema)
async def update_local_trip_package(
    payload: TripPackageUpdateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update a local trip package in the system configuration by id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update local trip packages.", status_code=403
        )
    return await update_trip_package_config(payload, db)


# Delete a local trip package by id
@router.delete("/{package_id}")
async def delete_local_trip_package(
    package_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Delete a local trip package in the system configuration by id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete local trip packages.", status_code=403
        )
    deleted= await delete_trip_package_config_by_id(package_id, db)
    return {"deleted": deleted}


# Get a local trip package by id
@router.get("/{package_id}", response_model=TripPackageSchema)
async def get_local_trip_package_by_id(
    package_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get a local trip package in the system configuration by id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view local trip packages.", status_code=403
        )
    return await get_trip_package_config_by_id(package_id, db)

#Activate a local trip package by id
@router.patch("/{package_id}/activate")
async def activate_local_trip_package(
    package_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Activate a local trip package in the system configuration by id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to activate local trip packages.", status_code=403
        )
    activated= await activate_trip_package_config_by_id(package_id, db)
    return {"activated": activated}
