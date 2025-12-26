from sqlalchemy.orm import Session

from core.security import RoleEnum
from models.cab.cab_orm import CabType
from models.cab.cab_schema import CabTypeSchema


def get_all_cabs(db: Session)-> list[CabTypeSchema]:
    """Retrieve all cabs from the database."""
    cabs = db.query(CabType).all()
    cab_schemas = [CabTypeSchema.model_validate(cab) for cab in cabs]
    return cab_schemas

def create_cabs(cabs:dict, db:Session):
    cab_types = []
    for car_type, data in cabs.items():
        cab_types.append(
            CabType(
                name=car_type,
                description=data["description"],
                cab_names=data["cab_names"],
                inventory_cab_names=data["inventory_cab_names"],
                capacity=data["capacity"],
                created_by=RoleEnum.system,
            )
        )
    
    db.add_all(cab_types)
    db.commit()