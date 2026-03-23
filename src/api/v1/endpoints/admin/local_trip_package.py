# Local trip package management endpoints for admin users - add, list, update and delete local trip packages in the system by region code, can be operated only by admin users like super_admin and regional_admin

from fastapi import APIRouter, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from models.trip.trip_schema import LocalTripPackageSchema, LocalTripPackageUpdateSchema, TripTypeSchema, TripTypeUpdateSchema
from models.user.user_orm import User
from db.database import a_yield_mysql_session
from sqlalchemy.ext.asyncio import AsyncSession

 


router = APIRouter()

#Add a new local trip package
@router.post("/add", response_model=LocalTripPackageSchema)
async def add_local_trip_package(
    payload: LocalTripPackageSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new local trip package to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.regional_admin]:
        raise CabboException(
            "You do not have permission to add local trip packages.", status_code=403
        )
    pass

#List all local trip packages
@router.get("/list", response_model=list[LocalTripPackageSchema])
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
    pass

#list all local trip packages by region code
@router.get("/list/{region_code}", response_model=list[LocalTripPackageSchema])
async def list_local_trip_packages_by_region_code(
    region_code: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all local trip packages in the system configuration for a specific region code."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.regional_admin]:
        raise CabboException(
            "You do not have permission to list local trip packages by region code.", status_code=403
        )
    pass

#Update a local trip package by id
@router.put("/update/{package_id}", response_model=LocalTripPackageSchema)
async def update_local_trip_package(
    package_id: str,
    payload: LocalTripPackageUpdateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update a local trip package in the system configuration by id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.regional_admin]:
        raise CabboException(
            "You do not have permission to update local trip packages.", status_code=403
        )
    pass

#Delete a local trip package by id
@router.delete("/delete/{package_id}")
async def delete_local_trip_package(
    package_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Delete a local trip package in the system configuration by id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.regional_admin]:
        raise CabboException(
            "You do not have permission to delete local trip packages.", status_code=403
        )
    pass

#Get a local trip package by id
@router.get("/{package_id}", response_model=LocalTripPackageSchema)
async def get_local_trip_package_by_id(
    package_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get a local trip package in the system configuration by id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.regional_admin]:
        raise CabboException(
            "You do not have permission to view local trip packages.", status_code=403
        )
    pass

