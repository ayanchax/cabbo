import requests
from functools import lru_cache
from typing import List, Optional, Union
from urllib.parse import urlencode

from core.config import settings
from models.map.location_schema import LocationInfo, LocationProximity
from utils.utility import safe_request

GOOGLE_API_KEY = settings.GOOGLE_MAPS_API_KEY
BASE_URL = "https://maps.googleapis.com/maps/api"


# ----------------------------------------
# UTIL
# ----------------------------------------

 

def _round_coord(val: float, precision: int = 4):
    return round(val, precision) if val is not None else None


# ----------------------------------------
# AUTOCOMPLETE (NO CACHE — SESSION BASED)
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

    url = f"{BASE_URL}/place/autocomplete/json"

    params = {
        "input": query,
        "key": GOOGLE_API_KEY,
    }

    if allowed_countries:
        params["components"] = ",".join([f"country:{c.lower()}" for c in allowed_countries])

    if proximity:
        params["location"] = f"{proximity.lat},{proximity.lng}"
        params["radius"] = 50000  # 50km bias

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
# PLACE DETAILS (CACHED)
# ----------------------------------------

@lru_cache(maxsize=2000)
def _cached_place_details(place_id: str):
    url = f"{BASE_URL}/place/details/json"

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
        url = f"{BASE_URL}/place/details/json"

        params = {
            "place_id": place_id,
            "key": GOOGLE_API_KEY,
            "sessiontoken": session_token,
        }

        data = safe_request(url, params)
    else:
        data = _cached_place_details(place_id)

    result = data.get("result")

    if not result:
        return None

    location = result["geometry"]["location"]

    return LocationInfo(
        display_name=result.get("name"),
        place_id=place_id,
        lat=location.get("lat"),
        lng=location.get("lng"),
        address=result.get("formatted_address"),
    )


# ----------------------------------------
# REVERSE GEOCODE (CACHED)
# ----------------------------------------

@lru_cache(maxsize=2000)
def _cached_reverse_geocode(lat: float, lng: float):
    url = f"{BASE_URL}/geocode/json"

    params = {
        "latlng": f"{lat},{lng}",
        "key": GOOGLE_API_KEY,
    }

    return safe_request(url, params)


def get_location_from_coordinates(lat: float, lng: float) -> Optional[LocationInfo]:
    data = _cached_reverse_geocode(_round_coord(lat), _round_coord(lng))

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
    )


# ----------------------------------------
# GEOGRAPHY EXTRACTION (CACHED VIA REVERSE)
# ----------------------------------------

def get_geography_from_coordinates(lat: float, lng: float):
    data = _cached_reverse_geocode(_round_coord(lat), _round_coord(lng))

    results = data.get("results", [])
    if not results:
        return {}

    components = results[0].get("address_components", [])

    geo = {
        "country": None,
        "country_code": None,
        "state": None,
        "state_code": None,
        "region": None,
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

        elif "locality" in types:
            geo["region"] = comp.get("long_name")

        elif "postal_code" in types:
            geo["postal_code"] = comp.get("long_name")

    return geo


# ----------------------------------------
# DISTANCE MATRIX (CACHED)
# ----------------------------------------

@lru_cache(maxsize=5000)
def _cached_distance(o_lat, o_lng, d_lat, d_lng):
    url = f"{BASE_URL}/distancematrix/json"

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
            _round_coord(o_lat),
            _round_coord(o_lng),
            _round_coord(d_lat),
            _round_coord(d_lng),
        )

        meters = data["rows"][0]["elements"][0]["distance"]["value"]
        return round(meters / 1000.0, 2)

    except Exception as e:
        print(f"[DISTANCE ERROR] {e}")
        return None


# ----------------------------------------
# STATE EXTRACTION
# ----------------------------------------

def get_state_from_location(location: Union[LocationInfo, dict, str]):
    if isinstance(location, LocationInfo):
        geo = get_geography_from_coordinates(location.lat, location.lng)
        return geo.get("state")

    return None