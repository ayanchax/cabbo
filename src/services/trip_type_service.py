# Add trip type

from core.security import RoleEnum
from models.trip.trip_orm import TripTypeMaster
from models.trip.trip_schema import TripTypeSchema, TripTypeUpdateSchema
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


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