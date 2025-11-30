from sqlalchemy.orm import Session

from core.security import RoleEnum
from models.cab.cab_orm import FuelType
from models.cab.cab_schema import FuelTypeSchema


def get_all_fuel_types(db: Session)-> list[FuelTypeSchema]:
    """Retrieve all fuel types."""
    fuel_types = db.query(FuelType).all()
    fuel_type_schemas = [FuelTypeSchema.model_validate(fuel) for fuel in fuel_types]
    return fuel_type_schemas

def create_fuel_types(fuel_types:list, db:Session):
    _fuel_types = [
        FuelType(
            name=fuel_type,
            created_by=RoleEnum.system
        )
        for fuel_type in fuel_types
    ]
    db.add_all(_fuel_types)
    db.commit()