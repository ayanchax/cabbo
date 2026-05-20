from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.config import settings
from core.exceptions import TRIP_PACKAGE_FETCH_FAILED, CabboException
from core.security import validate_customer_token
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_schema import TripPackageSchema
from services.trip_type_service import get_packages_by_region_code

router = APIRouter()


@router.get(
    "/packages/{trip_type}/{region_code}", response_model=list[TripPackageSchema]
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
