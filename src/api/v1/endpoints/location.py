from fastapi import APIRouter, Query
from typing import Union
from services.location_service import get_location_from_coordinates, get_location_suggestions, get_state_from_location, get_distance_km

router = APIRouter()


@router.get("/state")
def get_state(
    location: Union[str, None] = Query(
        None, description="Location name or lat,lng as 'lat,lng'"
    )
):
    """
    Get the state name for a given location (string or lat,lng as 'lat,lng').
    """
    # If lat,lng string, convert to dict
    if location and "," in location:
        try:
            lat, lng = map(float, location.split(","))
            location_obj = {"lat": lat, "lng": lng}
        except Exception:
            return {"error": "Invalid lat,lng format. Use 'lat,lng' or a place name."}
    else:
        location_obj = location
    state = get_state_from_location(location_obj)
    return {"state": state}


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
    query: str = Query(..., description="Partial location string to search for")
):
    """
    Get location suggestions based on a partial query string.
    """
    return get_location_suggestions(query)

@router.get("/reverse-geocode")
def reverse_geocode(
    lat: float = Query(..., description="Latitude for reverse geocoding"),
    lng: float = Query(..., description="Longitude for reverse geocoding"),
):
    """
    Get location details from latitude and longitude.
    """
    return get_location_from_coordinates(lat, lng)