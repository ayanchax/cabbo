from typing import Optional
from fastapi import APIRouter, Query
from customer_api.src.models.map.location_schema import LocationProximity
from customer_api.src.services.geography_service import get_allowed_countries
from customer_api.src.services.location_service import (
    get_location_from_coordinates,
    get_location_from_place_id,
    get_location_suggestions,
)

router = APIRouter()


@router.get("/search")
def search_location(
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
def reverse_geocode(
    lat: float = Query(..., description="Latitude for reverse geocoding"),
    lng: float = Query(..., description="Longitude for reverse geocoding"),
):
    """
    Get location details from latitude and longitude by reverse geocoding
    """
    return get_location_from_coordinates(lat, lng)


@router.get("/place-details")
def get_place_details(
    place_id: str = Query(..., description="Place ID to fetch details for"),
    session_token: Optional[str] = Query(
        None, description="Session token for caching and improving location suggestions"
    ),
):
    """
    Get location details from a place_id
    """
    return get_location_from_place_id(place_id, session_token=session_token)
