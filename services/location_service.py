from typing import Union
from models.geography.geo_enums import LocationInfo
from core.config import settings

provider = settings.LOCATION_SERVICE_PROVIDER


def get_state_from_location(location: Union[LocationInfo, dict, str]) -> str:
    if provider == "mapbox":
        from services.mapbox_service import get_state_from_location as mapbox_get_state

        return mapbox_get_state(location)
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
