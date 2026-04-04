from fastapi import APIRouter
from . import (
    airport_cab_pricing as airport_cab_pricing_ep,
    trip_common_pricing as trip_common_pricing_ep,
    trip_package_pricing as trip_package_pricing_ep,
    fixed_platform_pricing as fixed_platform_pricing_ep,
    local_cab_pricing as local_cab_pricing_ep,
    outstation_cab_pricing as outstation_cab_pricing_ep,
    night_pricing as night_pricing_ep,
    permit_fee_pricing as permit_fee_pricing_ep,
)

# Not attaching -pricing suffix because the endpoint parent router already has /pricing prefix. So the final endpoint will be /admin/config/pricing/airport-cab, /admin/config/pricing/trip-common etc.
router = APIRouter()
router.include_router(
    airport_cab_pricing_ep.router,
    prefix="/airport-cab",
    tags=["admin-airport-cab-pricing-configuration"],
)
router.include_router(
    trip_common_pricing_ep.router,
    prefix="/common",
    tags=["admin-trip-common-pricing-configuration"],
)
router.include_router(
    trip_package_pricing_ep.router,
    prefix="/package",
    tags=["admin-trip-package-pricing-configuration"],
)
router.include_router(
    fixed_platform_pricing_ep.router,
    prefix="/platform",
    tags=["admin-fixed-platform-pricing-configuration"],
)
router.include_router(
    local_cab_pricing_ep.router,
    prefix="/local-cab",
    tags=["admin-local-cab-pricing-configuration"],
)
router.include_router(
    outstation_cab_pricing_ep.router,
    prefix="/outstation-cab",
    tags=["admin-outstation-cab-pricing-configuration"],
)
router.include_router(
    night_pricing_ep.router,
    prefix="/night",
    tags=["admin-night-pricing-configuration"],
)
router.include_router(
    permit_fee_pricing_ep.router,
    prefix="/permit",
    tags=["admin-permit-fee-pricing-configuration"],
)
