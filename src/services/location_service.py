from typing import List, Union
from models.map.location_schema import LocationInfo, LocationProximity
from core.config import settings

provider = settings.LOCATION_SERVICE_PROVIDER


def get_state_from_location(location: Union[LocationInfo, dict, str], state_code=False) -> Union[str, None]:
    if provider == "google":
        from services.google_map_service import (
            get_state_from_location as google_get_state,
        )

        return google_get_state(location)
    return None


def get_distance_km(
    origin: Union[LocationInfo, dict, str], destination: Union[LocationInfo, dict, str]
):
    if provider == "google":
        from services.google_map_service import get_distance_km as google_get_distance

        return google_get_distance(origin, destination)
    return None


def get_location_suggestions(query: str, allowed_countries:List[str], proximity:Union[LocationProximity,None]=None, limit:int=5) -> List[LocationInfo]:
    """
    Given a partial location string, return a list of suggested addresses/locations using the configured provider.
    Each suggestion should be a dict with at least 'display_name', 'lat', 'lng', and optionally 'place_id' or 'address'.
    """
    if provider == "google":
        from services.google_map_service import (
            get_location_suggestions as google_suggest,
        )

        return google_suggest(query, allowed_countries=allowed_countries, proximity=proximity, limit=limit)
    return []


def get_location_from_coordinates(lat: float, lng: float):
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