import sys
from pathlib import Path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from functools import lru_cache
from typing import List, Optional, Union
from urllib.parse import quote, quote_plus
from core.config import settings
from models.map.location_schema import LocationInfo, LocationProximity, MobilityHub
from utils.utility import log_lru_cache, round_value, safe_request
import logging
log = logging.getLogger(__name__)
GOOGLE_API_KEY = settings.GOOGLE_MAPS_API_KEY
BASE_URL = "https://maps.googleapis.com/maps/api"
PLACES_BASE_URL = "https://places.googleapis.com/v1/places"
PLACES_NEARBY_SEARCH_API = f"{PLACES_BASE_URL}:searchNearby"
PUBLIC_PLACES_URL = "https://www.google.com/maps/search/?api=1"
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
            display_name=p.get("structured_formatting", {}).get("main_text") or p.get("description"),
            address=p.get("structured_formatting", {}).get("secondary_text") or p.get("description"),
            place_id=p.get("place_id"),
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
    mobility_hub_place_id = None
    mobility_hub = (
        _extract_mobility_hub(result.get("types", []))
        or _infer_mobility_hub_from_name(result.get("name"))
    )
    # If mobility_hub is still None, try to infer from nearby airport sub-places.
    if mobility_hub is None:
        mobility_hub, mobility_hub_place_id = _infer_airport_subplace_from_nearby_places(
            result.get("name"), location.get("lat"), location.get("lng")
        )
    #In future, we can keep on inferring mobility hub from other nearby places like bus stations, railway stations, etc. But for now, we are only inferring airport sub-places as that is the most common use case and we do not cater to railway/bus station pickup and drop off yet. So we will keep it simple for now and only infer airport sub-places.

    return LocationInfo(
        display_name=result.get("name"),
        place_id=place_id,
        lat=location.get("lat"),
        lng=location.get("lng"),
        address=result.get("formatted_address"),
        mobility_hub=mobility_hub,
        mobility_hub_place_id=mobility_hub_place_id,
        **geo,
    )


# Maps Google place types to MobilityHub enum values (priority order — first match wins)
_GOOGLE_MOBILITY_TYPE_MAP: dict[str, MobilityHub] = {
    "airport": MobilityHub.airport,
    "international_airport": MobilityHub.airport,
    "train_station": MobilityHub.railway_station,
    "bus_station": MobilityHub.bus_station,
    "taxi_stand": MobilityHub.taxi_stand,
    "subway_station": MobilityHub.subway_station,
    "light_rail_station": MobilityHub.transit_station,
    "transit_station": MobilityHub.transit_station,
}


_NEARBY_AIRPORT_FIELD_MASK = "places.id,places.primaryType,places.types"
_AIRPORT_SUBPLACE_SEARCH_RADIUS_METERS = 5000.0
_AIRPORT_SUBPLACE_KEYWORDS = (
    "terminal",
    "arrival",
    "arrivals",
    "departure",
    "departures",
)
_NON_AIRPORT_TERMINAL_KEYWORDS = (
    "bus",
    "railway",
    "train",
    "metro",
    "subway",
    "ferry",
    "port",
)


def _extract_mobility_hub(types: list) -> Optional[MobilityHub]:
    """Return the first MobilityHub match from a Google place types list."""
    for t in (types or []):
        hub = _GOOGLE_MOBILITY_TYPE_MAP.get(t)
        if hub:
            return hub
    return None


def _extract_mobility_hub_from_place_context(place: dict) -> Optional[MobilityHub]:
    """Extract a mobility hub from a Places API (New) place payload."""
    return _extract_mobility_hub(
        [place.get("primaryType")] + place.get("types", [])
    )


@lru_cache(maxsize=2000)
def _cached_nearby_airport_places(lat: float, lng: float):
    headers = {
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": _NEARBY_AIRPORT_FIELD_MASK,
    }
    body = {
        "includedTypes": ["airport"],
        "maxResultCount": 3,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": lat,
                    "longitude": lng,
                },
                "radius": _AIRPORT_SUBPLACE_SEARCH_RADIUS_METERS,
            }
        },
    }

    return safe_request(
        PLACES_NEARBY_SEARCH_API,
        headers=headers,
        method="POST",
        json=body,
    )


def _infer_airport_subplace_from_nearby_places(
    name: Optional[str],
    lat: Optional[float],
    lng: Optional[float],
) -> tuple[Optional[MobilityHub], Optional[str]]:
    """Classify airport sub-places when Google finds an airport around them."""
    if lat is None or lng is None or not name:
        return None, None

    name_lower = name.lower()
    if not any(keyword in name_lower for keyword in _AIRPORT_SUBPLACE_KEYWORDS):
        return None, None
    if any(keyword in name_lower for keyword in _NON_AIRPORT_TERMINAL_KEYWORDS):
        return None, None

    data = _cached_nearby_airport_places(round_value(lat), round_value(lng))
    log_lru_cache("nearby_airport_places", _cached_nearby_airport_places)

    for place in data.get("places", []):
        if _extract_mobility_hub_from_place_context(place) == MobilityHub.airport:
            # Return the first nearby airport place ID along with the mobility hub type.
            # In future we can return all nearby airports and let the user choose, but for now we just return the first one as this is more practical for our use case (airport sub-places). Plus also within a 5km radius there is usually only one airport anyway.
            return MobilityHub.airport, place.get("id")

    return None, None


# Ordered most-specific first so generic "station" never shadows "railway station" etc.
_MOBILITY_NAME_KEYWORDS: list[tuple[str, MobilityHub]] = [
    ("airport",          MobilityHub.airport),
    ("aerodrome",        MobilityHub.airport),
    ("railway station",  MobilityHub.railway_station),
    ("train station",    MobilityHub.railway_station),
    ("metro station",    MobilityHub.subway_station),
    ("subway station",   MobilityHub.subway_station),
    ("bus station",      MobilityHub.bus_station),
    ("bus stand",        MobilityHub.bus_station),
    ("bus terminus",     MobilityHub.bus_station),
    ("bus terminal",     MobilityHub.bus_station),
    ("taxi stand",       MobilityHub.taxi_stand),
    # broad catch-all — handles "SMVT Bengaluru Station", "Majestic Station" etc.
    # intentionally last to avoid false positives (police station, petrol station, etc.)
    ("station",          MobilityHub.transit_station),
]


def _infer_mobility_hub_from_name(name: Optional[str]) -> Optional[MobilityHub]:
    """Keyword fallback: infer mobility hub from a place name when type-based detection fails."""
    if not name:
        return None
    name_lower = name.lower()
    for keyword, hub in _MOBILITY_NAME_KEYWORDS:
        if keyword in name_lower:
            return hub
    return None


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

def _extract_display_name_from_components(components: list) -> Optional[str]:
    # Build a 2-part display name: "<route or sublocality>, <area>"
    # e.g. "Kodigehalli Rd, Battarahalli" or "Padmeshwari Nagar, Battarahalli"
    buckets = {}
    for comp in components:
        for t in comp.get("types", []):
            if t not in buckets:
                buckets[t] = comp.get("long_name")

    primary = (
        buckets.get("establishment")
        or buckets.get("route")
        or buckets.get("sublocality_level_2")
        or buckets.get("sublocality_level_1")
        or buckets.get("sublocality")
        or buckets.get("locality")
    )
    secondary = (
        buckets.get("sublocality_level_1")
        or buckets.get("locality")
    ) if primary != buckets.get("sublocality_level_1") and primary != buckets.get("locality") else None

    if primary and secondary:
        return f"{primary}, {secondary}"
    return primary or (components[0].get("long_name") if components else None)

# ----------------------------------------
# PLACE API - END
# ----------------------------------------

# ----------------------------------------
# PLACE MAP URL API - CACHE ONLY
# ----------------------------------------

def _build_maps_search_url(place_id: str) -> str:
    return (
        f"{PUBLIC_PLACES_URL}"
        f"&query={quote_plus('place')}"
        f"&query_place_id={quote_plus(place_id)}"
    )


@lru_cache(maxsize=2000)
def _cached_google_maps_uri(place_id: str):
    url = f"{PLACES_BASE_URL}/{quote(place_id, safe='')}"
    headers = {
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "googleMapsUri,googleMapsLinks.placeUri",
    }

    return safe_request(url, headers=headers)


@lru_cache(maxsize=2000)
def _cached_place_url(place_id: str):
    params = {
        "place_id": place_id,
        "fields": "url",
        "key": GOOGLE_API_KEY,
    }

    return safe_request(PLACE_API, params)


def get_google_map_url_from_place_id(place_id: str) -> Optional[str]:
    if not place_id or not place_id.strip():
        return None

    cleaned_place_id = place_id.strip()
    data = _cached_google_maps_uri(cleaned_place_id)
    log_lru_cache("google_maps_uri", _cached_google_maps_uri)

    legacy_data = _cached_place_url(cleaned_place_id)
    log_lru_cache("place_url", _cached_place_url)

    return (
        data.get("googleMapsUri")
        or data.get("googleMapsLinks", {}).get("placeUri")
        or legacy_data.get("result", {}).get("url")
        or _build_maps_search_url(cleaned_place_id)
    )

# ----------------------------------------
# PLACE MAP URL API - END
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
    address_components = result.get("address_components", [])
    geo = _extract_geo_from_components(address_components)
    display_name = _extract_display_name_from_components(address_components)
    loc = result.get("geometry", {}).get("location")
    # Reverse geocode returns multiple results; scan all for a mobility hub match
    # (the first result is often administrative, the establishment type may appear further down)
    mobility_hub = (
        next(
            (hub for r in results if (hub := _extract_mobility_hub(r.get("types", [])))),
            None,
        )
        or _infer_mobility_hub_from_name(display_name)
    )
    return LocationInfo(
        place_id=result.get("place_id"),
        lat=loc.get("lat") if loc else lat,
        lng=loc.get("lng") if loc else lng,
        address=result.get("formatted_address"),
        display_name=display_name,
        mobility_hub=mobility_hub,
        **geo,
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
