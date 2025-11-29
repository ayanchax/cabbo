from sqlalchemy.orm import Session

from models.cab.cab_orm import CabType
from models.cab.cab_schema import CabTypeSchema


def get_all_cabs(db: Session)-> list[CabTypeSchema]:
    """Retrieve all cabs from the database."""
    cabs = db.query(CabType).all()
    cab_schemas = [CabTypeSchema.model_validate(cab) for cab in cabs]
    return cab_schemas