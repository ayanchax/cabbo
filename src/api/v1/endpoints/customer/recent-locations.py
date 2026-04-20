from fastapi import (
    APIRouter,
    Depends,
    Path,
    Query,
)
from sqlalchemy.orm import Session
from db.database import a_yield_mysql_session, yield_mysql_session
from models.customer.customer_orm import Customer
from models.customer.passenger_schema import (
    PassengerCreate,
    PassengerOut,
    PassengerUpdate,
)
from models.customer.recent_location_schema import RecentLocationCreate, RecentLocationRead
from models.map.location_schema import LocationInfo
from services.customer_service import (
    get_active_customer_by_id,
)

from core.security import validate_customer_token
from core.exceptions import CabboException
from services.passenger_service import (
    create_passenger,
    delete_passenger,
    is_passenger_belongs_to_customer,
    update_passenger,
)
from services.recent_location_service import get_recent_locations_for_customer, save_recent_location
from services.validation_service import (
    validate_passenger_payload,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

# Recent locations endpoints for customers to view and manage their recent pickup and dropoff locations which they can then associate with their trip bookings. This will allow customers to easily manage their frequently used locations and associate them with their trips for a smoother booking experience. These endpoints will also validate the JWT token to ensure that only authenticated customers can manage their recent locations and that they can only manage recent locations associated with their own account for privacy and security reasons.


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