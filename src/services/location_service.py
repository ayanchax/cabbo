import math
from typing import List, Optional, Union
from models.map.location_schema import LocationInfo, LocationProximity
from core.config import settings

provider = settings.LOCATION_SERVICE_PROVIDER


_EARTH_RADIUS_KM = 6371  # mean radius of the Earth in kilometres
_ROAD_TORTUOSITY_FACTOR = 1.2  # straight-line → estimated road distance multiplier, simulates real-world routing without API calls


def get_distance_km_haversine(
    origin: LocationInfo,
    destination: LocationInfo,
) -> Optional[float]:
    """
    Estimated road distance in km derived from the Haversine straight-line distance
    scaled by a tortuosity factor (1.2) to approximate real road routing.
    Free — no external API call.
    Use for classification thresholds and zero-distance guards where
    exact road distance is not required.
    """
    try:
        lat1 = math.radians(origin.lat)
        lon1 = math.radians(origin.lng)
        lat2 = math.radians(destination.lat)
        lon2 = math.radians(destination.lng)
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        straight_line_km = 2 * _EARTH_RADIUS_KM * math.asin(math.sqrt(a))
        return round(straight_line_km * _ROAD_TORTUOSITY_FACTOR, 2)
    except Exception:
        return None


def get_distance_km(
    origin: Union[LocationInfo, dict, str], destination: Union[LocationInfo, dict, str], 
):
    if provider == "google":
        from services.google_map_service import get_distance_km as google_get_distance

        return google_get_distance(origin, destination)
    return None


def get_location_suggestions(query: str, allowed_countries:List[str], proximity:Union[LocationProximity,None]=None, limit:int=5, session_token:Optional[str]=None) -> List[LocationInfo]:
    """
    Given a partial location string, return a list of suggested addresses/locations using the configured provider.
    Each suggestion should be a dict with at least 'display_name', 'lat', 'lng', and optionally 'place_id' or 'address'.
    """
    if provider == "google":
        from services.google_map_service import (
            get_location_suggestions as google_suggest,
        )

        return google_suggest(query, allowed_countries=allowed_countries, proximity=proximity, limit=limit, session_token=session_token)
    return []


def get_location_from_coordinates(lat: float, lng: float) -> Optional[LocationInfo]:
    """
    Given latitude and longitude, return the corresponding location details using the configured provider.
    The returned location details should include 'display_name', 'lat', 'lng', and optionally 'place_id' or 'address'.
    """
    if provider == "google":
        from services.google_map_service import (
            get_location_from_coordinates as google_reverse,
        )

        return google_reverse(lat, lng)
    return None

def get_location_from_place_id(place_id: str, session_token:Optional[str]=None) -> Optional[LocationInfo]:    
    """
    Given a place_id, return the corresponding location details using the configured provider.
    The returned location details should include 'display_name', 'lat', 'lng', and optionally 'address'.
    """
    if provider == "google":
        from services.google_map_service import (
            get_location_from_place_id as google_place_details,
        )

        return google_place_details(place_id, session_token=session_token)
    return None


def get_map_url_from_place_id(place_id: str) -> Optional[str]:
    """
    Given a Google place_id, return a Google Maps URL for that place.
    """
    if provider == "google":
        from services.google_map_service import (
            get_google_map_url_from_place_id as google_map_url,
        )

        return google_map_url(place_id)
    return None


def remove_extra_fields_from_location(location_details: dict):
    keys_to_remove = ["country", "region", "state", "postal_code"]
    for key in keys_to_remove:
        location_details.pop(key, None)
    return location_details
