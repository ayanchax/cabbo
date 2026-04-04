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
    async_add_airport_to_region,
    async_add_car_type_to_region,
    async_add_fuel_type_to_region,
    async_add_region,
    async_add_trip_type_to_region,
    async_delete_region,
    async_get_all_regions,
    async_get_region_by_id,
    async_remove_airport_from_region,
    async_remove_car_type_from_region,
    async_remove_fuel_type_from_region,
    async_remove_trip_type_from_region,
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

#Get region by id
@router.get("/{region_id}", response_model=RegionSchema)
async def get_region(region_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Retrieve a region/city by its ID."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to view regions.", status_code=403
        )
    region = await async_get_region_by_id(region_id=region_id, db=db)
    if not region:
        raise CabboException(status_code=404, message="Region not found")
    return region

@router.put(
    "/{region_id}",
    response_model=RegionSchema,
)
async def update_region(
    region_id: str,
    payload: RegionUpdate,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update an existing region/city's configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update regions.", status_code=403
        )
    payload.id = region_id  # Ensure the payload includes the region ID for update
    result, error = await async_update_region(payload=payload, db=db)
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

# Add airport in a region, input will be airport_id and region_id
@router.post("/{region_id}/add-airport/{airport_id}")
async def add_airport_to_region(region_id: str, airport_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Add an airport to a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to add airport to region goes here
    success, error = await async_add_airport_to_region(region_id=region_id, airport_id=airport_id, db=db)
    if not success:
        raise CabboException(error or "Failed to add airport to region", status_code=400)
    return {"detail": f"Airport {airport_id} added to region {region_id} successfully."}

# Delete/pop airport from a region, input will be airport_id and region_id
@router.delete("/{region_id}/remove-airport/{airport_id}")
async def remove_airport_from_region(region_id: str, airport_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Remove an airport from a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to remove airport from region goes here
    success, error = await async_remove_airport_from_region(region_id=region_id, airport_id=airport_id, db=db)
    if not success:
        raise CabboException(error or "Failed to remove airport from region", status_code=400)
    return {"detail": f"Airport {airport_id} removed from region {region_id} successfully."}

# Add trip type id to region, input will be trip_type_id and region_id
@router.post("/{region_id}/add-trip-type/{trip_type_id}")
async def add_trip_type_to_region(region_id: str, trip_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Add a trip type to a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to add trip type to region goes here
    success, error = await async_add_trip_type_to_region(region_id=region_id, trip_type_id=trip_type_id, db=db)
    if not success:
        raise CabboException(error or "Failed to add trip type to region", status_code=400)
    return {"detail": f"Trip type {trip_type_id} added to region {region_id} successfully."}

# Remove trip type id from region, input will be trip_type_id and region_id
@router.delete("/{region_id}/remove-trip-type/{trip_type_id}")
async def remove_trip_type_from_region(region_id: str, trip_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Remove a trip type from a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to remove trip type from region goes here
    success, error = await async_remove_trip_type_from_region(region_id=region_id, trip_type_id=trip_type_id, db=db)
    if not success:
        raise CabboException(error or "Failed to remove trip type from region", status_code=400)
    return {"detail": f"Trip type {trip_type_id} removed from region {region_id} successfully."}

# Add fuel type id to region, input will be fuel_type_id and region_id
@router.post("/{region_id}/add-fuel-type/{fuel_type_id}")
async def add_fuel_type_to_region(region_id: str, fuel_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Add a fuel type to a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to add fuel type to region goes here
    success, error = await async_add_fuel_type_to_region(region_id=region_id, fuel_type_id=fuel_type_id, db=db)
    if not success:
        raise CabboException(error or "Failed to add fuel type to region", status_code=400)
    return {"detail": f"Fuel type {fuel_type_id} added to region {region_id} successfully."}

# Remove fuel type id from region, input will be fuel_type_id and region_id
@router.delete("/{region_id}/remove-fuel-type/{fuel_type_id}")
async def remove_fuel_type_from_region(region_id: str, fuel_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Remove a fuel type from a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to remove fuel type from region goes here
    success, error = await async_remove_fuel_type_from_region(region_id=region_id, fuel_type_id=fuel_type_id, db=db)
    if not success:
        raise CabboException(error or "Failed to remove fuel type from region", status_code=400)
    return {"detail": f"Fuel type {fuel_type_id} removed from region {region_id} successfully."}

# Add car type id to region, input will be car_type_id and region_id
@router.post("/{region_id}/add-car-type/{car_type_id}")
async def add_car_type_to_region(region_id: str, car_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Add a car type to a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to add car type to region goes here
    success, error = await async_add_car_type_to_region(region_id=region_id, car_type_id=car_type_id, db=db)
    if not success:
        raise CabboException(error or "Failed to add car type to region", status_code=400)
    return {"detail": f"Car type {car_type_id} added to region {region_id} successfully."}

# Remove car type id from region, input will be car_type_id and region_id
@router.delete("/{region_id}/remove-car-type/{car_type_id}")
async def remove_car_type_from_region(region_id: str, car_type_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Remove a car type from a region."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to modify regions.", status_code=403
        )
    # Implementation to remove car type from region goes here
    success, error = await async_remove_car_type_from_region(region_id=region_id, car_type_id=car_type_id, db=db)
    if not success:
        raise CabboException(error or "Failed to remove car type from region", status_code=400)
    return {"detail": f"Car type {car_type_id} removed from region {region_id} successfully."}