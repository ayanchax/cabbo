from typing import Union
from models.geography.geo_enums import LocationInfo
from core.config import settings

provider = settings.LOCATION_SERVICE_PROVIDER


def get_state_from_location(location: Union[LocationInfo, dict, str], state_code=False) -> Union[str, None]:
    if provider == "mapbox":
        from services.mapbox_service import get_state_from_location as mapbox_get_state

        return mapbox_get_state(location=location,state_code=state_code)
    elif provider == "google":
        from services.google_map_service import (
            get_state_from_location as google_get_state,
        )

        return google_get_state(location)
    return None


def get_distance_km(
    origin: Union[LocationInfo, dict, str], destination: Union[LocationInfo, dict, str]
):
    if provider == "mapbox":
        from services.mapbox_service import get_distance_km as mapbox_get_distance

        return mapbox_get_distance(origin, destination)
    elif provider == "google":
        from services.google_map_service import get_distance_km as google_get_distance

        return google_get_distance(origin, destination)
    return None


def get_location_suggestions(query: str):
    """
    Given a partial location string, return a list of suggested addresses/locations using the configured provider.
    Each suggestion should be a dict with at least 'display_name', 'lat', 'lng', and optionally 'place_id' or 'address'.
    """
    if provider == "mapbox":
        from services.mapbox_service import get_location_suggestions as mapbox_suggest

        return mapbox_suggest(query)
    elif provider == "google":
        from services.google_map_service import (
            get_location_suggestions as google_suggest,
        )

        return google_suggest(query)
    return []
