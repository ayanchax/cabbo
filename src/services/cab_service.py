
from typing import Union
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from core.security import RoleEnum
from models.cab.cab_orm import CabType
from models.cab.cab_schema import CabTypeSchema, CabTypeUpdateSchema
import logging

from models.trip.trip_enums import CarTypeEnum
from models.trip.trip_schema import TripSearchRequest
log = logging.getLogger(__name__)
def get_all_cabs(db: Session)-> list[CabTypeSchema]:
    """Retrieve all cabs from the database."""
    cabs = db.query(CabType).all()
    cab_schemas = [CabTypeSchema.model_validate(cab) for cab in cabs]
    return cab_schemas

def create_cabs(cabs:dict, db:Session, created_by:RoleEnum=RoleEnum.system):
    cab_types = []
    for car_type, data in cabs.items():
        cab_types.append(
            CabType(
                name=car_type,
                description=data["description"],
                cab_names=data["cab_names"],
                inventory_cab_names=data["inventory_cab_names"],
                capacity=data["capacity"],
                created_by=created_by,
            )
        )
    try:
        db.bulk_save_objects(cab_types)  # More efficient for bulk inserts
        db.flush()  # Flush to assign IDs before commit
    except Exception as e:
        log.error(f"Error seeding cab types: {e}")



async def add_new_cab_type(cab_type: CabTypeSchema, db: AsyncSession, created_by:RoleEnum=RoleEnum.system) -> Union[CabTypeSchema, None]:
    """Add a new cab type to the database."""
    new_cab = CabType(
        name=cab_type.name,
        description=cab_type.description,
        cab_names=cab_type.cab_names,
        inventory_cab_names=cab_type.inventory_cab_names,
        capacity=cab_type.capacity,
        created_by=created_by
    )
    try:
        db.add(new_cab)
        await db.commit()
        await db.refresh(new_cab)
        return CabTypeSchema.model_validate(new_cab)
    except Exception as e:
        await db.rollback()
        log.error(f"Error adding cab type: {e}")
        return None
    
async def async_get_all_cabs(db: AsyncSession) -> list[CabTypeSchema]:
    """Retrieve all cab types from the database."""
    result = await db.execute(select(CabType))
    cabs = result.scalars().all()
    return [CabTypeSchema.model_validate(cab) for cab in cabs]

async def get_cab_type_by_id(cab_type_id: str, db: AsyncSession) -> Union[CabTypeSchema, None]:
    """Retrieve a cab type by its ID."""
    result = await db.execute(select(CabType).where(CabType.id == cab_type_id))
    cab = result.scalar_one_or_none()
    if cab:
        return CabTypeSchema.model_validate(cab)
    return None

async def async_delete_cab_type(cab_type_id: str, db: AsyncSession) -> tuple[bool, Union[str, None]]:
    """Delete a cab type from the database."""
    try:
        result = await db.execute(select(CabType).where(CabType.id == cab_type_id))
        cab = result.scalar_one_or_none()
        if cab is None:
            return False, f"Cab type with id {cab_type_id} not found."
        if cab.is_active == False:
            return False, "Cab type is already inactive."
        cab.is_active=False  # Soft delete by marking as inactive
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        log.error(f"Error deleting cab type: {e}")
        return False, str(e)
    
async def async_update_cab_type(cab_type_data: CabTypeUpdateSchema, db: AsyncSession) -> Union[CabTypeSchema, None]:
    """Update an existing cab type in the database."""
    try:
        if not cab_type_data.id:
            return None  # ID is required for update
        result = await db.execute(select(CabType).where(CabType.id == cab_type_data.id))
        cab = result.scalar_one_or_none()
        if cab is None:
            return None
    
        for field, value in cab_type_data.model_dump(exclude_unset=True, exclude={"id"}).items():
            setattr(cab, field, value)
        await db.commit()
        await db.refresh(cab)
        return CabTypeSchema.model_validate(cab)
    except Exception as e:
        await db.rollback()
        log.error(f"Error updating cab type: {e}")
        return None

async def async_activate_cab(cab_type_id:str, db:AsyncSession):
     try:
        result = await db.execute(select(CabType).where(CabType.id == cab_type_id))
        cab = result.scalar_one_or_none()
        if cab is None:
            return False, f"Cab type with id {cab_type_id} not found."
        if cab.is_active:
            return False, f"Cab type with id {cab_type_id} is already active."
        cab.is_active=True
        await db.commit()
        return True, None
     except Exception as e:
        await db.rollback()
        log.error(f"Error activating cab type: {e}")
        return False, str(e)

def get_car_type_rank(car_type: CarTypeEnum) -> int:
    car_type_rank = {
        CarTypeEnum.hatchback: 0,
        CarTypeEnum.sedan: 1,
        CarTypeEnum.sedan_plus: 2,
        CarTypeEnum.suv: 3,
        CarTypeEnum.suv_plus: 4,
    }
    return car_type_rank.get(car_type, -1)  # Return -1 for unknown car types
 
def get_recommended_car_type(
    total_num_people: int,
    total_num_luggages: int,
) -> CarTypeEnum:
    """
    Selects the smallest car type that can comfortably support passenger and luggage totals.
    """
    if total_num_people > 6:
        passenger_car_type = CarTypeEnum.suv_plus
    elif total_num_people >= 5:
        passenger_car_type = CarTypeEnum.suv
    elif total_num_people >= 4:
        passenger_car_type = CarTypeEnum.sedan_plus
    elif total_num_people >= 2:
        passenger_car_type = CarTypeEnum.sedan
    else:
        passenger_car_type = CarTypeEnum.hatchback

    if total_num_luggages > 4:
        luggage_car_type = CarTypeEnum.suv_plus
    elif total_num_luggages >= 4:
        luggage_car_type = CarTypeEnum.suv
    elif total_num_luggages >= 3:
        luggage_car_type = CarTypeEnum.sedan_plus
    elif total_num_luggages >= 2:
        luggage_car_type = CarTypeEnum.sedan
    else:
        luggage_car_type = CarTypeEnum.hatchback

    if get_car_type_rank(luggage_car_type) > get_car_type_rank(passenger_car_type):
        return luggage_car_type
    return passenger_car_type
