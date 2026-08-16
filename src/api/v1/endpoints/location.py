from typing import Optional
from fastapi import APIRouter, Depends, Query
from core.exceptions import PLACE_NOT_FOUND, CabboException
from core.security import validate_customer_token, validate_user_token
from models.customer.customer_orm import Customer
from models.map.location_schema import MapUrl, LocationProximity
from models.user.user_orm import User
from services.geography_service import get_allowed_countries
from services.location_service import (
    get_map_url_from_place_id,
    get_location_from_coordinates,
    get_location_from_place_id,
    get_location_suggestions,
)

router = APIRouter()


@router.get("/search")
async def search_location(
    _: Customer = Depends(validate_customer_token),
    query: str = Query(..., description="Partial location string to search for"),
    lat: float = Query(None, description="Optional latitude to bias results"),
    lng: float = Query(None, description="Optional longitude to bias results"),
    limit: int = Query(5, description="Maximum number of suggestions to return"),
    session_token: Optional[str] = Query(
        None, description="Session token for caching and improving location suggestions"
    ),
):
    """
    Get location suggestions based on a partial query string.
    """

    return get_location_suggestions(
        query,
        allowed_countries=get_allowed_countries(),
        proximity=LocationProximity(lat=lat, lng=lng) if lat and lng else None,
        limit=limit,
        session_token=session_token,
    )


@router.get("/reverse-geocode")
async def reverse_geocode(
    _: Customer = Depends(validate_customer_token),
    lat: float = Query(..., description="Latitude for reverse geocoding"),
    lng: float = Query(..., description="Longitude for reverse geocoding"),
):
    """
    Get location details from latitude and longitude by reverse geocoding
    """
    return get_location_from_coordinates(lat, lng)


@router.get("/place-details")
async def get_place_details(
    _: Customer = Depends(validate_customer_token),
    place_id: str = Query(..., description="Place ID to fetch details for"),
    session_token: Optional[str] = Query(
        None, description="Session token for caching and improving location suggestions"
    ),
):
    """
    Get location details from a place_id
    """
    return get_location_from_place_id(place_id, session_token=session_token)


@router.get("/mapurl", response_model=MapUrl)
async def get_map_url(
    _: User = Depends(validate_user_token),
    place_id: str = Query(..., description="Maps place ID to generate a map URL for"),
):
    """
    Get a Maps URL from a place_id.
    """
    map_url = get_map_url_from_place_id(place_id)
    if not map_url:
        raise CabboException(
            "Could not generate Maps URL for the provided place_id",
            status_code=404,
            error_code=PLACE_NOT_FOUND,
        )

    return MapUrl(place_id=place_id.strip(), map_url=map_url)
