from sqlalchemy.orm import Session

from models.cab.cab_orm import FuelType
from models.cab.cab_schema import FuelTypeSchema


def get_all_fuel_types(db: Session)-> list[FuelTypeSchema]:
    """Retrieve all fuel types."""
    fuel_types = db.query(FuelType).all()
    fuel_type_schemas = [FuelTypeSchema.model_validate(fuel) for fuel in fuel_types]
    return fuel_type_schemas