from fastapi import APIRouter

from ..admin.geography import country as country_ep

from ..admin.geography import region as region_ep
from ..admin.geography import state as state_ep
router = APIRouter()
router.include_router(country_ep.router, prefix="/countries", tags=["admin-geography-country"])
router.include_router(state_ep.router, prefix="/states", tags=["admin-geography-state"]) 
router.include_router(region_ep.router, prefix="/regions", tags=["admin-geography-region"])