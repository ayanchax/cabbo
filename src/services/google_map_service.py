import sys
from pathlib import Path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from functools import lru_cache
from typing import List, Optional, Union
from core.config import settings
from models.map.location_schema import LocationInfo, LocationProximity
from utils.utility import log_lru_cache, round_value, safe_request
import logging
log = logging.getLogger(__name__)
GOOGLE_API_KEY = settings.GOOGLE_MAPS_API_KEY
BASE_URL = "https://maps.googleapis.com/maps/api"
AUTOCOMPLETE_API = f"{BASE_URL}/place/autocomplete/json"
PLACE_API = f"{BASE_URL}/place/details/json"
DISTANCE_API = f"{BASE_URL}/distancematrix/json"
GEOCODE_API = f"{BASE_URL}/geocode/json"

# Notes:
# Google session tokens apply ONLY to:

# Autocomplete
# Place Details

# 👉 Not:

# Distance Matrix
# Geocode


# ----------------------------------------
# 1. AUTOCOMPLETE API - SESSION TOKEN
# ----------------------------------------

def get_location_suggestions(
    query: str,
    allowed_countries: Optional[List[str]] = ["IN"],
    limit: int = 5,
    proximity: Optional[LocationProximity] = None,
    session_token: Optional[str] = None,
):
    if not query or len(query.strip()) < 2:
        return []

    url = AUTOCOMPLETE_API

    params = {
        "input": query,
        "key": GOOGLE_API_KEY,
    }

    if allowed_countries:
        params["components"] = ",".join(
            [f"country:{c.lower()}" for c in allowed_countries]
        )

    if proximity:
        params["location"] = f"{proximity.lat},{proximity.lng}"
        params["radius"] = (
            proximity.radius_km * 1000 if proximity.radius_km else 50000
        )  # Convert km to meters

    if session_token:
        params["sessiontoken"] = session_token
    data = safe_request(url, params)
    predictions = data.get("predictions", [])[:limit]

    return [
        LocationInfo(
            display_name=p.get("description"),
            place_id=p.get("place_id"),
            address=p.get("description"),
        )
        for p in predictions
    ]

# ----------------------------------------
# AUTOCOMPLETE API - END
# ----------------------------------------

# ----------------------------------------
# 2. PLACE API - SESSION TOKEN + CACHE
# ----------------------------------------

@lru_cache(maxsize=2000)
def _cached_place_details(place_id: str):
    url = PLACE_API

    params = {
        "place_id": place_id,
        "key": GOOGLE_API_KEY,
    }

    return safe_request(url, params)


def get_location_from_place_id(
    place_id: str,
    session_token: Optional[str] = None,
) -> Optional[LocationInfo]:

    # Use cache ONLY if session_token is None
    if session_token:
        url = PLACE_API

        params = {
            "place_id": place_id,
            "key": GOOGLE_API_KEY,
            "sessiontoken": session_token,
        }

        data = safe_request(url, params)
    else:
        data = _cached_place_details(place_id)
        log_lru_cache(
            "place_details", _cached_place_details
        )  # Log cache stats for place details

    result = data.get("result")

    if not result:
        return None

    location = result["geometry"]["location"]
    address_components = result.get("address_components", [])
    geo = _extract_geo_from_components(address_components)
    return LocationInfo(
        display_name=result.get("name"),
        place_id=place_id,
        lat=location.get("lat"),
        lng=location.get("lng"),
        address=result.get("formatted_address"),
        **geo,
    )


def _extract_geo_from_components(components: list) -> dict:
    geo = {
        "country": None,
        "country_code": None,
        "state": None,
        "state_code": None,
        "region": None,
        "region_code": None,
        "postal_code": None,
    }

    for comp in components:
        types = comp.get("types", [])

        if "country" in types:
            geo["country"] = comp.get("long_name")
            geo["country_code"] = comp.get("short_name")

        elif "administrative_area_level_1" in types:
            geo["state"] = comp.get("long_name")
            geo["state_code"] = comp.get("short_name")

        elif "locality" in types or "administrative_area_level_2" in types:
            geo["region"] = comp.get("long_name")
            geo["region_code"] = comp.get("short_name")

        elif "postal_code" in types:
            geo["postal_code"] = comp.get("long_name")

    return geo

# ----------------------------------------
# PLACE API - END
# ----------------------------------------

# ----------------------------------------
# 3. GEOCODE API (NO SESSION TOKEN - CACHE ONLY)
# ----------------------------------------

@lru_cache(maxsize=2000)
def _cached_reverse_geocode(lat: float, lng: float):
    url = GEOCODE_API

    params = {
        "latlng": f"{lat},{lng}",
        "key": GOOGLE_API_KEY,
    }

    return safe_request(url, params)

def get_location_from_coordinates(lat: float, lng: float) -> Optional[LocationInfo]:
    data = _cached_reverse_geocode(round_value(lat), round_value(lng))
    log_lru_cache(
        "reverse_geocode", _cached_reverse_geocode
    )  # Log cache stats for reverse geocode
    results = data.get("results", [])
    if not results:
        return None

    result = results[0]

    return LocationInfo(
        display_name=result.get("formatted_address"),
        place_id=result.get("place_id"),
        lat=lat,
        lng=lng,
        address=result.get("formatted_address"),
        **result,
    )

# ----------------------------------------
# GEOCODE API - END
# ----------------------------------------

# ----------------------------------------
# 4. DISTANCE API - (NO SESSION TOKEN - CACHE ONLY)
# ----------------------------------------

@lru_cache(maxsize=5000)
def _cached_distance(o_lat, o_lng, d_lat, d_lng):
    url = DISTANCE_API

    params = {
        "origins": f"{o_lat},{o_lng}",
        "destinations": f"{d_lat},{d_lng}",
        "key": GOOGLE_API_KEY,
    }

    return safe_request(url, params)

def get_distance_km(
    origin: Union[LocationInfo, dict, str],
    destination: Union[LocationInfo, dict, str],
):
    try:
        o_lat, o_lng = origin.lat, origin.lng
        d_lat, d_lng = destination.lat, destination.lng

        data = _cached_distance(
            round_value(o_lat),
            round_value(o_lng),
            round_value(d_lat),
            round_value(d_lng),
        )
        log_lru_cache(
            "distance_matrix", _cached_distance
        )  # Log cache stats for distance matrix

        meters = data["rows"][0]["elements"][0]["distance"]["value"]
        return round(meters / 1000.0, 2)

    except Exception as e:
        log.error(f"[DISTANCE ERROR] {e}")
        return None

# ----------------------------------------
# DISTANCE API - END
# ----------------------------------------
