#Include all routers in endpoints

from fastapi import APIRouter

router = APIRouter()

# Core endpoints
from api.v1.endpoints import auth as auth_ep, customer as customer_ep, location as location_ep, seed as seed_ep, trip as trip_ep

router.include_router(auth_ep.router, prefix="/auth", tags=["auth"])
router.include_router(customer_ep.router, prefix="/customers", tags=["customers"])
router.include_router(location_ep.router, prefix="/locations", tags=["locations"])
router.include_router(seed_ep.router, prefix="/seed", tags=["seed"])
router.include_router(trip_ep.router, prefix="/trips", tags=["trips"])

# Admin endpoints (group under /admin/*)
from api.v1.endpoints.admin import auth as admin_auth_ep, driver as admin_driver_ep, user as admin_user_ep

router.include_router(admin_auth_ep.router, prefix="/admin/auth", tags=["admin-auth"])
#router.include_router(admin_customer_ep.router, prefix="/admin/customers", tags=["admin-customers"])
router.include_router(admin_driver_ep.router, prefix="/admin/drivers", tags=["admin-drivers"])
router.include_router(admin_user_ep.router, prefix="/admin/users", tags=["admin-users"])
