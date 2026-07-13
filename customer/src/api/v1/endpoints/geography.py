from fastapi import APIRouter
from customer_api.src.services.geography_service import get_geography_data

router = APIRouter()


@router.get("/")
async def get_geography():
    return await get_geography_data()
