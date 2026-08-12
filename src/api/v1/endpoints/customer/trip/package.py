from fastapi import APIRouter, Depends
from core.security import validate_customer_token
from models.customer.customer_orm import Customer
from models.pricing.pricing_schema import TripPackageConfigRead, TripPackageConfigSchema
from models.trip.trip_enums import TripTypeEnum
from services.trip_type_service import get_packages_by_region_code

router = APIRouter()


@router.get(
    "/{trip_type}/{region_code}", response_model=list[TripPackageConfigRead]
)
async def get_packages(
    trip_type: TripTypeEnum,
    region_code: str,
    _: Customer = Depends(validate_customer_token),
):
    packages = get_packages_by_region_code(
        trip_type=trip_type, region_code=region_code,  
    )
    # Sort packages by included_hours ascending
    packages_sorted = sorted(packages, key=lambda p: p.included_hours)
    # Only return id, included_hours, included_km and description in the response
    return [
        TripPackageConfigSchema(
            id=package.id,
            included_hours=package.included_hours,
            included_km=package.included_km,
            best_intended_for=package.best_intended_for
        )
        for package in packages_sorted
    ]
    


