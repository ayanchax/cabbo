# Include all routers in endpoints

from fastapi import APIRouter

from api.v1.endpoints import (
    fuel as fuel_config_ep,
    housekeeping as admin_housekeeping_ep,
    kyc_document_types as admin_kyc_document_types_ep,
    local_trip_package as admin_trip_package_ep,
    trip_type as admin_trip_type_ep,
)
from api.v1.endpoints.geography.geo_routes import router as geography_config_ep
from api.v1.endpoints.pricing.pricing_routes import router as pricing_config_ep
from api.v1.endpoints import user as admin_user_ep
from api.v1.endpoints.trip import trip as admin_trip_ep
from api.v1.endpoints import (
    airport as admin_airport_ep,
    auth as admin_auth_ep,
    cab as cab_config_ep,
    customer as admin_customer_ep,
    driver as admin_driver_ep,
)

router = APIRouter()


router.include_router(admin_auth_ep.router, prefix="/admin/auth", tags=["admin-auth"])
router.include_router(
    admin_customer_ep.router, prefix="/admin/customers", tags=["admin-customers"]
)
router.include_router(
    admin_driver_ep.router, prefix="/admin/drivers", tags=["admin-drivers"]
)
router.include_router(admin_user_ep.router, prefix="/admin/users", tags=["admin-users"])

router.include_router(geography_config_ep, prefix="/admin/config/geography")
router.include_router(pricing_config_ep, prefix="/admin/config/pricing")
router.include_router(
    cab_config_ep.router, prefix="/admin/config/cab", tags=["admin-cab-configuration"]
)
router.include_router(
    fuel_config_ep.router,
    prefix="/admin/config/fuel",
    tags=["admin-fuel-configuration"],
)
router.include_router(
    admin_airport_ep.router,
    prefix="/admin/config/airport",
    tags=["admin-airport-configuration"],
)
router.include_router(
    admin_kyc_document_types_ep.router,
    prefix="/admin/config/kyc-document-types",
    tags=["admin-kyc-document-types-configuration"],
)


router.include_router(admin_trip_ep.router, prefix="/admin/trips")
router.include_router(
    admin_trip_type_ep.router,
    prefix="/admin/config/trip-types",
    tags=["admin-trip-type-configuration"],
)
router.include_router(
    admin_trip_package_ep.router,
    prefix="/admin/config/trip-packages",
    tags=["admin-trip-package-configuration"],
)

router.include_router(
    admin_housekeeping_ep.router,
    prefix="/admin/housekeeping",
    tags=["admin-housekeeping"],
)
