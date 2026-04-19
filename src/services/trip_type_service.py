# Add trip type

from typing import Optional

from core.security import RoleEnum
from core.store import ConfigStore
from models.map.location_schema import LocationInfo
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import TripTypeMaster
from models.trip.trip_schema import TripTypeSchema, TripTypeUpdateSchema
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.location_service import get_distance_km
from services.trips.outstation_service import get_outstation_min_distance
from core.config import settings

async def async_add_trip_type(
    trip_type_data: TripTypeSchema, db: AsyncSession, created_by: RoleEnum= RoleEnum.system
):
    """Asynchronously add a new trip type to the database."""
    try:
        new_trip_type = TripTypeMaster(
            trip_type=trip_type_data.trip_type,
            display_name=trip_type_data.display_name,
            description=trip_type_data.description,
            created_by=created_by,
        )
        db.add(new_trip_type)
        await db.commit()
        await db.refresh(new_trip_type)
        return TripTypeSchema.model_validate(new_trip_type), None
    except Exception as e:
        await db.rollback()
        return None, str(e)

async def async_get_all_trip_types(db: AsyncSession):
    """Asynchronously retrieve all trip types from the database."""
    result = await db.execute(select(TripTypeMaster))
    trip_types = result.scalars().all()
    return [TripTypeSchema.model_validate(trip_type) for trip_type in trip_types]

async def async_update_trip_type(trip_type_data: TripTypeUpdateSchema, db: AsyncSession):
    """Asynchronously update an existing trip type in the database."""
    try:
        result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_data.id))
        trip_type = result.scalar_one_or_none()
        if not trip_type:
            return None, "Trip type not found"
        if trip_type_data.description:
            trip_type.description = trip_type_data.description
        if trip_type_data.display_name:
            trip_type.display_name = trip_type_data.display_name
        if trip_type_data.trip_type:
            trip_type.trip_type = trip_type_data.trip_type

        await db.commit()
        await db.refresh(trip_type)
        return TripTypeSchema.model_validate(trip_type), None
    except Exception as e:
        await db.rollback()
        return None, str(e)
    
async def async_delete_trip_type(trip_type_id: str, db: AsyncSession):
    """Asynchronously delete a trip type from the database."""
    try:
        result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_id))
        trip_type = result.scalar_one_or_none()
        if not trip_type:
            return False, "Trip type not found"
        if not trip_type.is_active:
            return False, "Trip type is already inactive"
        trip_type.is_active = False # Soft delete by marking as inactive
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)
    
async def async_activate_trip_type(trip_type_id: str, db: AsyncSession):
    """Asynchronously activate a trip type in the database."""
    try:
        result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_id))
        trip_type = result.scalar_one_or_none()
        if not trip_type:
            return False, "Trip type not found"
        if trip_type.is_active:
            return False, "Trip type is already active"
        trip_type.is_active = True
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)
    
async def async_get_trip_type_by_id(trip_type_id: str, db: AsyncSession):
    """Asynchronously retrieve a trip type by its ID from the database."""
    result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_id))
    trip_type = result.scalar_one_or_none()
    if trip_type:
        return TripTypeSchema.model_validate(trip_type)
    return None

async def async_get_trip_type_by_name(trip_type_name: TripTypeEnum, db: AsyncSession):
    """Asynchronously retrieve a trip type by its name from the database."""
    result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.trip_type == trip_type_name))
    trip_type = result.scalar_one_or_none()
    if trip_type:
        return TripTypeSchema.model_validate(trip_type)
    return None


def classify_trip_type(
    pickup: LocationInfo,
    dropoff: Optional[LocationInfo],
    config_store: ConfigStore=None,
) -> TripTypeEnum:
    if not config_store:
        from db.database import get_mysql_local_session
        syncdb = get_mysql_local_session()
        config_store = settings.get_config_store(db=syncdb)

    # Rule 1: No dropoff → local (hourly rental, no fixed destination)
    if not dropoff:
        return TripTypeEnum.local

    # Build airport place_id set for O(1) lookup
    airport_place_ids = {
        airport.place_id
        for airport in (config_store.airport_locations or [])
        if airport.place_id
    }

    # Rule 2: Airport detection — first-satisfier, pickup takes priority over dropoff
    if pickup.place_id and pickup.place_id in airport_place_ids:
        return TripTypeEnum.airport_pickup

    if dropoff.place_id and dropoff.place_id in airport_place_ids:
        return TripTypeEnum.airport_drop

    # Rule 3: Distance-based classification
    distance = get_distance_km(origin=pickup, destination=dropoff)
    if distance is None:
        # Cannot calculate — default to local (non-blocking; /search will validate)
        return TripTypeEnum.local

    outstation_min_km = get_outstation_min_distance(
        pickup=pickup, config_store=config_store
    )
    if outstation_min_km and distance >= outstation_min_km:
        return TripTypeEnum.outstation

    return TripTypeEnum.local


