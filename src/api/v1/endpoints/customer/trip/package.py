from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.security import validate_customer_token
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from models.pricing.pricing_schema import TripPackageConfigSchema
from models.trip.trip_enums import TripTypeEnum
from services.trip_type_service import get_packages_by_region_code

router = APIRouter()


@router.get(
    "/{trip_type}/{region_code}", response_model=list[TripPackageConfigSchema]
)
def get_packages(
    trip_type: TripTypeEnum,
    region_code: str,
    db: Session = Depends(yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    return get_packages_by_region_code(
        trip_type=trip_type, region_code=region_code, db=db
    )


