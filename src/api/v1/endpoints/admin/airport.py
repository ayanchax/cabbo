# - Airport endpoints for adding, listing, updating and deleting airports in a region, can be
# operated only by super admin

from fastapi import APIRouter, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.airport.airport_schema import AirportSchema, AirportUpdateSchema
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession

from services.airport_service import (
    async_activate_airport,
    async_add_airport,
    async_delete_airport,
    async_get_airport_by_id,
    async_get_airport_by_region_code,
    async_get_all_airports,
    async_get_all_airports_in_country,
    async_get_all_airports_in_state,
    async_update_airport,
)


router = APIRouter()


@router.post("/add")
async def add_airport(
    payload: AirportSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new airport to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to add airports.", status_code=403
        )
    airport, error = await async_add_airport(
        airport_data=payload, db=db, created_by=current_user_role
    )
    if error:
        raise CabboException(error, status_code=400)
    if not airport:
        raise CabboException("Failed to add new airport", status_code=500)
    return airport


@router.get("/list", response_model=list[AirportSchema])
async def list_airports(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all airports in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view airports.", status_code=403
        )
    airports = await async_get_all_airports(db)
    return airports


# Get airport by id
@router.get("/{airport_id}", response_model=AirportSchema)
async def get_airport(
    airport_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Retrieve an airport by its ID."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view airports.", status_code=403
        )
    airport = await async_get_airport_by_id(airport_id=airport_id, db=db)
    if not airport:
        raise CabboException(status_code=404, message="Airport not found")
    return airport

 

#Get all airports in a state with a state code. There can be multiple airports in a state.
@router.get("/state/{state_code}", response_model=list[AirportSchema])
async def get_airports_by_state(
    state_code: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Retrieve all airports in a specific state by state code."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view airports.", status_code=403
        )
    airports = await async_get_all_airports_in_state(state_code=state_code, db=db)
    return airports

#Get all airports in a country with a country code. There are multiple airports in a country.
@router.get("/country/{country_code}", response_model=list[AirportSchema])
async def get_airports_by_country(
    country_code: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Retrieve all airports in a specific country by country code."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view airports.", status_code=403
        )
    airports = await async_get_all_airports_in_country(country_code=country_code, db=db)
    return airports

#Get all airports in a region with a region code. There can be multiple airports in a region.
@router.get("/region/{region_code}", response_model=list[AirportSchema])
async def get_airports_by_region(
    region_code: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Retrieve all airports in a specific region by region code."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view airports.", status_code=403
        )
    airports = await async_get_airport_by_region_code(region_code=region_code, db=db)
    if not airports:
        raise CabboException(status_code=404, message="No airports found for the specified region")
    return airports

@router.put("/{airport_id}", response_model=AirportSchema)
async def update_airport(
    airport_id: str,
    payload: AirportUpdateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update an existing airport's configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update airports.", status_code=403
        )
    airport, error = await async_update_airport(
        airport_id=airport_id, airport_data=payload, db=db
    )
    if error:
        raise CabboException(error, status_code=400)
    if not airport:
        raise CabboException("Failed to update airport", status_code=500)
    return airport


# Activate airport
@router.patch("/{airport_id}/activate")
async def activate_airport(
    airport_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Activate an airport in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to activate airports.", status_code=403
        )
    success, error_message = await async_activate_airport(airport_id=airport_id, db=db)
    if not success:
        raise CabboException(
            status_code=400, message=error_message or "Failed to activate airport"
        )
    return {"message": "Airport activated successfully"}


@router.delete("/{airport_id}")
async def delete_airport(
    airport_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Delete an airport from the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete airports.", status_code=403
        )
    success, error = await async_delete_airport(airport_id=airport_id, db=db)
    if error:
        raise CabboException(error, status_code=400)
    if not success:
        raise CabboException("Failed to delete airport", status_code=500)
    return {"message": "Airport deleted successfully"}
