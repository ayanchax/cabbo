from typing import List

from fastapi import (
    APIRouter,
    Depends,
)
from db.database import yield_mysql_session
from models.cab.cab_schema import CabTypeSchema
from models.customer.customer_orm import Customer
from sqlalchemy.orm import Session
from core.security import validate_customer_token

from services.configuration_service import get_all_cabs
router = APIRouter()


# Get all fleets available in the system, this can be used by customers to view the different fleets they can choose from when booking a trip.
@router.get("/", response_model=List[CabTypeSchema])
def get_all_fleets(
    db: Session = Depends(yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    return get_all_cabs(db) 