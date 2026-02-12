from fastapi import APIRouter
from fastapi.params import Depends
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.geography.country_schema import CountrySchema, CountryUpdateSchema
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession

from services.geography_service import async_activate_country, async_add_country, async_delete_country, async_get_all_countries, async_get_country_by_id, async_set_default_country, async_update_country

router = APIRouter()
# Country Management
@router.post(
    "/add", response_model=CountrySchema, 
)
async def add_country(country: CountrySchema, db: AsyncSession = Depends(a_yield_mysql_session),current_user: User = Depends(validate_user_token),):
    """Add a new country to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to add countries.", status_code=403
        )
    result = await async_add_country(payload=country, db=db, created_by=current_user_role)
    if not result:
        raise CabboException(status_code=500, message="Failed to add new country")
    return result


@router.get(
    "/list",
    response_model=list[CountrySchema],
    
)
def list_countries(db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """List all countries in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to view countries.", status_code=403
        )
    # Implementation to fetch and return list of countries goes here
    return async_get_all_countries(db=db)

#Get country by id
@router.get("/{country_id}", response_model=CountrySchema)
async def get_country(country_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Retrieve a country by its ID."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to view countries.", status_code=403
        )
    country = await async_get_country_by_id(country_id=country_id, db=db)
    
    if not country:
        raise CabboException(status_code=404, message="Country not found")
    return country

#Patch default country
@router.patch("/{country_id}/default")
async def set_default_country(country_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Set a country as the default country in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to set default country.", status_code=403
        )
    success, error = await async_set_default_country(country_id=country_id, db=db)
    if error:
        raise CabboException(status_code=500, message=error)
    if not success:
        raise CabboException(status_code=404, message="Country not found")
    return {"detail": f"Country {country_id} set as default successfully."}

@router.put(
    "/{country_id}",
    response_model=CountrySchema,
    
)
async def update_country(country: CountryUpdateSchema, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Update an existing country's configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update countries.", status_code=403
        )
    result, error = await async_update_country(payload=country, db=db)
    if not result:
        raise CabboException(status_code=500, message=error or "Failed to update country")
    return result

#Activate a country
@router.patch("/{country_id}/activate")
async def activate_country(country_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Activate a country in the system configuration.""" 
    current_user_role = current_user.role 
    if current_user_role not in [RoleEnum.super_admin]: 
        raise CabboException( "You do not have permission to activate countries.", status_code=403 ) 
    result, error = await async_activate_country(country_id=country_id, db=db) 
    if not result: 
        raise CabboException(status_code=500, message=error or "Failed to activate country") 
    return {"detail": f"Country {country_id} activated successfully."}


@router.delete("/{country_id}" )
async def delete_country(country_id: str, db: AsyncSession = Depends(a_yield_mysql_session), current_user: User = Depends(validate_user_token)):
    """Delete a country from the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete countries.", status_code=403
        )
    result, error = await async_delete_country(country_id=country_id, db=db)
    if not result:
        raise CabboException(status_code=500, message=error or "Failed to delete country")
    return {"detail": f"Country {country_id} deleted successfully."}

