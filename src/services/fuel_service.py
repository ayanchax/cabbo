from sqlalchemy.orm import Session

from core.exceptions import CabboException
from core.security import RoleEnum
from models.cab.cab_orm import FuelType
from models.cab.cab_schema import FuelTypeSchema
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


def get_all_fuel_types(db: Session)-> list[FuelTypeSchema]:
    """Retrieve all fuel types."""
    fuel_types = db.query(FuelType).all()
    fuel_type_schemas = [FuelTypeSchema.model_validate(fuel) for fuel in fuel_types]
    return fuel_type_schemas

def create_fuel_types(fuel_types:list, db:Session, created_by:RoleEnum=RoleEnum.system):
    _fuel_types = [
        FuelType(
            name=fuel_type,
            created_by=created_by
        )
        for fuel_type in fuel_types
    ]
    try:
        db.bulk_save_objects(_fuel_types)  # More efficient for bulk inserts
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Error seeding fuel types: {e}")

async def async_add_fuel_type(fuel_type: FuelTypeSchema, db: AsyncSession, created_by: RoleEnum = RoleEnum.system) -> FuelTypeSchema:
    """Asynchronously add a new fuel type to the database."""
    try:
        new_fuel_type = FuelType(
            name=fuel_type.name,
            created_by=created_by
        )
        db.add(new_fuel_type)
        await db.commit()
        await db.refresh(new_fuel_type)
        return FuelTypeSchema.model_validate(new_fuel_type)
    except Exception as e:
        await db.rollback()
        print(f"Error adding fuel type: {e}")
        return None

async def async_get_all_fuel_types(db: AsyncSession) -> list[FuelTypeSchema]:
    """Asynchronously retrieve all fuel types from the database."""
    result = await db.execute(select(FuelType))
    fuel_types = result.scalars().all()
    fuel_type_schemas = [FuelTypeSchema.model_validate(fuel) for fuel in fuel_types]
    return fuel_type_schemas

async def async_delete_fuel_type(fuel_type_id: str, db: AsyncSession)-> tuple[bool, str | None]:
    """Asynchronously delete a fuel type from the database."""
    try:
        result = await db.execute(select(FuelType).where(FuelType.id == fuel_type_id))
        fuel_type = result.scalar_one_or_none()
        if fuel_type is None:
            return False, "Fuel type not found"
        if fuel_type.created_by == RoleEnum.system:
            return False , "Cannot delete system-defined fuel types"
        
        fuel_type.is_active = False  # Soft delete by marking as inactive
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        print(f"Error deleting fuel type: {e}")
        return False, str(e)

async def async_update_fuel_type(fuel_type_data: FuelTypeSchema, db: AsyncSession) -> FuelTypeSchema | None:
    """Asynchronously update an existing fuel type in the database."""
    try:
        if not fuel_type_data.id:
            raise CabboException(status_code=400, detail="Fuel type ID is required for update") 
        
        result = await db.execute(select(FuelType).where(FuelType.id == fuel_type_data.id))
        fuel_type = result.scalar_one_or_none()
        if fuel_type is None:
            return None
        if fuel_type.created_by == RoleEnum.system:
            raise CabboException(status_code=403, detail="Cannot update system-defined fuel types")
        
        fuel_type.name = fuel_type_data.name
        await db.commit()
        await db.refresh(fuel_type)
        return FuelTypeSchema.model_validate(fuel_type)
    except Exception as e:
        await db.rollback()
        print(f"Error updating fuel type: {e}")
        return None