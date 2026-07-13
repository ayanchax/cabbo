from fastapi import (
    APIRouter,
    Depends,
    Query,
)
from customer_api.src.db.database import a_yield_mysql_session
from customer_api.src.models.customer.customer_orm import Customer
from customer_api.src.models.map.location_schema import LocationInfo

from customer_api.src.core.security import validate_customer_token
from customer_api.src.services.recent_location_service import get_recent_locations_for_customer, save_recent_location
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# Recent locations endpoints for customers to view and manage their recent pickup and dropoff locations which they can then associate with their trip bookings. 
# This will allow customers to easily manage their frequently used locations and associate them with their trips for a smoother booking experience. 
# These endpoints will also validate the JWT token to ensure that only authenticated customers can manage their recent locations and that they can only manage 
# recent locations associated with their own account for privacy and security reasons.

# No admin based endpoints for recent locations as this data is 
# specific to each customer and does not require administrative oversight or management.
# Also no delete endpoint for recent locations as they will be automatically managed based 
# on usage and recency, and customers can simply stop using a location 
# if they no longer want it to appear in their recent locations list. 
# This approach keeps the user experience simple and intuitive 
# while still allowing customers to have control over their recent locations through their usage patterns.


@router.post("/save", response_model = LocationInfo)
async def add_recent_location(
    payload: LocationInfo,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    recent_location= await save_recent_location(current_customer.id, payload, db)
    return recent_location.location

@router.get("/", response_model=list[LocationInfo])
async def get_recent_locations(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
    limit: int = Query(5, description="Number of recent locations to retrieve")
):
    recent_locations = await get_recent_locations_for_customer(current_customer.id, db, limit)
    return [loc.location for loc in recent_locations]