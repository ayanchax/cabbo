from models.customer.recent_location_orm import CustomerRecentLocation
from models.customer.recent_location_schema import RecentLocationRead
from models.map.location_schema import LocationInfo
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from core.config import settings

async def save_recent_location(customer_id: str, location: LocationInfo, db: AsyncSession):
    existing = await db.execute(
        select(CustomerRecentLocation)
        .where(
            CustomerRecentLocation.customer_id == customer_id,
            CustomerRecentLocation.place_id == location.place_id,
        )
    )
    existing = existing.scalar_one_or_none()

    location_payload = location.model_dump()  # or model_dump()
    new_record=None
    if existing:
        existing.usage_count += 1
        existing.last_used_at = datetime.now(datetime.timezone.utc)
        existing.location = location_payload  # keep fresh
    else:
        new_record = CustomerRecentLocation(
            customer_id=customer_id,
            place_id=location.place_id,
            provider=settings.LOCATION_SERVICE_PROVIDER,
            location=location_payload,
        )
        db.add(new_record)


    await db.commit()
    record = existing if existing else new_record
    return RecentLocationRead.model_validate(record)

async def get_recent_locations_for_customer(customer_id: str, db: AsyncSession, limit:int=5):
    try:
        result = await db.execute(
            select(CustomerRecentLocation)
            .where(CustomerRecentLocation.customer_id == customer_id)
            .order_by(CustomerRecentLocation.last_used_at.desc(),
                      CustomerRecentLocation.usage_count.desc())
            .limit(limit)
        )
        records = result.scalars().all()
        return [RecentLocationRead.model_validate(record) for record in records]
    except Exception as e:
        print(f"Error fetching recent locations for customer {customer_id}: {e}")
        return []