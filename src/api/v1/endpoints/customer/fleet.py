from typing import List

from fastapi import (
    APIRouter,
    Depends,
)
from db.database import a_yield_mysql_session
from models.cab.cab_schema import CabTypeSchema
from models.customer.customer_orm import Customer
from services.cab_service import async_get_all_cabs

from core.security import validate_customer_token
from sqlalchemy.ext.asyncio import AsyncSession
router = APIRouter()


# Get all fleets available in the system, this can be used by customers to view the different fleets they can choose from when booking a trip.
@router.get("/", response_model=List[CabTypeSchema])
async def view_driver_profile(
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    return await async_get_all_cabs(db)