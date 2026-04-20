from fastapi import APIRouter, Query
from models.map.location_schema import LocationProximity
from services.geography_service import get_allowed_countries
from services.location_service import (
    get_location_from_coordinates,
    get_location_suggestions,
    get_distance_km,
)

router = APIRouter()


@router.get("/distance")
def get_distance(
    origin: str = Query(..., description="Origin as place name or 'lat,lng'"),
    destination: str = Query(..., description="Destination as place name or 'lat,lng'"),
):
    """
    Get the driving distance in km between two locations (place names or lat,lng).
    """

    def parse_loc(loc):
        if "," in loc:
            try:
                lat, lng = map(float, loc.split(","))
                return {"lat": lat, "lng": lng}
            except Exception:
                return loc  # fallback to string
        return loc

    origin_obj = parse_loc(origin)
    destination_obj = parse_loc(destination)
    distance = get_distance_km(origin_obj, destination_obj)
    return {"distance_km": distance}


@router.get("/search")
def search_location(
    query: str = Query(..., description="Partial location string to search for"),
    lat: float = Query(None, description="Optional latitude to bias results"),
    lng: float = Query(None, description="Optional longitude to bias results"),
    limit: int = Query(5, description="Maximum number of suggestions to return"),
):
    """
    Get location suggestions based on a partial query string.
    """
    
    return get_location_suggestions(
        query,
        allowed_countries=get_allowed_countries(),
        proximity=LocationProximity(lat=lat, lng=lng) if lat and lng else None,
        limit=limit
    )


@router.get("/reverse-geocode")
def reverse_geocode(
    lat: float = Query(..., description="Latitude for reverse geocoding"),
    lng: float = Query(..., description="Longitude for reverse geocoding"),
):
    """
    Get location details from latitude and longitude.
    """
    return get_location_from_coordinates(lat, lng)
