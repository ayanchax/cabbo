#Driver related endpoints for customers to view driver profiles and ratings etc.
from fastapi import (
    APIRouter,
    Depends,
    Path,
)
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from models.driver.driver_schema import DriverReadSchema
from services.driver_service import a_get_driver_by_id, get_average_rating_by_driver_id

from core.security import validate_customer_token
from core.exceptions import CabboException
from sqlalchemy.ext.asyncio import AsyncSession
router = APIRouter()


# See driver profile by ID, availablle to customers for viewing driver details before/after booking a trip with them. 
@router.get("/{driver_id}", response_model=DriverReadSchema)
async def view_driver_profile(
    driver_id: str = Path(..., description="ID of the driver"),
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    """View driver details/profile."""
    driver =  await a_get_driver_by_id(driver_id=driver_id, db=db)
    if not driver or driver.is_active==False:
        raise CabboException(
            f"Driver with id {driver_id} not found.",
            status_code=404,
        )
    return DriverReadSchema.model_validate(driver)

# See avg rating of a driver, available to customers for viewing driver avg rating before/after booking a trip with them.
@router.get("/{driver_id}/average-rating", response_model=float)
async def get_average_rating_of_driver(
    driver_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    """Get the average rating of a driver."""
    return await get_average_rating_by_driver_id(driver_id=driver_id, db=db)
