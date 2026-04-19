from functools import lru_cache
import sys
from pathlib import Path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from typing import List, Optional, Union
from models.map.location_schema import LocationInfo, LocationProximity
from core.config import settings
from urllib.parse import quote
from utils.utility import log_lru_cache, safe_request
from db.database import get_mysql_local_session
from models.airport.airport_schema import AirportSchema
from services.airport_service import get_all_airports_configuration


MAPBOX_TOKEN = settings.MAPBOX_TOKEN
MAPBOX_BASE_URL = "https://api.mapbox.com"
DEBUG_LRU_CACHE = settings.DEBUG_LRU_CACHE


def _get_airport_features(query: str) -> List[dict]:
    airport_features=[]
    if "airport" in query:
        all_airports:List[AirportSchema]=[]
        with get_mysql_local_session() as db:
            config_store = settings.get_config_store(db)
            all_airports = get_all_airports_configuration(config_store)
        for airport in all_airports:
            airport_feature = {
                "id": f"airport.{airport.place_id}",
                "place_name": f"{airport.display_name}, {airport.region}, {airport.state}, {airport.country}",
                "center": [airport.lng, airport.lat],
                "place_type": ["poi", "airport"],
                "relevance": 1.0,
                "properties": {
                    "short_code": None,
                    "wikidata": None,
                },
                "context": [
                    {
                        "id": f"country.{airport.country_code.lower()}",
                        "text": airport.country,
                        "short_code": airport.country_code.lower(),
                    },
                    {
                        "id": f"region.{airport.state_code.lower()}",
                        "text": airport.state,
                        "short_code": airport.state_code.lower(),
                    },
                    {
                        "id": f"place.{airport.region_code.lower()}",
                        "text": airport.region,
                        "short_code": airport.region_code.lower(),
                    },
                ],
            }
            airport_features.append(airport_feature)
    
    return airport_features

def _normalize_query(query: str):
    return query.strip().lower()


def _get_directions(o_lng, o_lat, d_lng, d_lat):
    url = f"{MAPBOX_BASE_URL}/directions/v5/mapbox/driving/{o_lng},{o_lat};{d_lng},{d_lat}"

    params = {
        "access_token": MAPBOX_TOKEN,
        "geometries": "geojson",
    }

    return safe_request(url, params)


@lru_cache(maxsize=1000)
def _cached_directions(o_lng, o_lat, d_lng, d_lat):
    return _get_directions(o_lng, o_lat, d_lng, d_lat)


def _reverse_geocode(lat: float, lng: float) -> dict:
    url = f"{MAPBOX_BASE_URL}/geocoding/v5/mapbox.places/{lng},{lat}.json"

    params = {
        "access_token": MAPBOX_TOKEN,
        "limit": 1,
    }

    return safe_request(url, params)


@lru_cache(maxsize=1000)
def _cached_reverse_geocode(lat: float, lng: float):
    return _reverse_geocode(lat, lng)


def _forward_geocode(query: str, params: dict) -> dict:
    url = f"{MAPBOX_BASE_URL}/geocoding/v5/mapbox.places/{quote(query)}.json"
    params = {**params, "access_token": MAPBOX_TOKEN}
    return safe_request(url, params)


@lru_cache(maxsize=500)
def _cached_forward_geocode(
    query: str, country_key: Optional[str], prox_key: Optional[str], limit: int
):
    url = f"{MAPBOX_BASE_URL}/geocoding/v5/mapbox.places/{quote(query)}.json"

    params = {
        "access_token": MAPBOX_TOKEN,
        "limit": limit or 5,
    }

    if country_key:
        params["country"] = country_key.split(",")

    if prox_key:
        params["proximity"] = prox_key

    return safe_request(url, params)


@lru_cache(maxsize=1000)
def get_geography_from_coordinates_cached(lat: float, lng: float) -> dict:
    return get_geography_from_coordinates(lat, lng)


def get_geography_from_coordinates(lat: float, lng: float) -> dict:

    geojson = _cached_reverse_geocode(lat, lng)
    if DEBUG_LRU_CACHE:
        log_lru_cache("reverse", _cached_reverse_geocode)

    if not geojson or "features" not in geojson:
        print(f"Mapbox returned invalid response for coordinates: {lat}, {lng}")
        return {}

    features = geojson.get("features", [])

    if not features:
        print(f"No features found in Mapbox response for coordinates: {lat}, {lng}")
        return {}

    feature = features[0]

    geography = _extract_geography_from_context(feature)

    return {
        "country": geography.get("country"),
        "country_code": geography.get("country_code"),
        "state": geography.get("state"),
        "state_code": geography.get("state_code"),
        "region": geography.get("region"),
        "region_code": geography.get("region_code"),
        "postal_code": geography.get("postal_code"),
        "address": feature.get("place_name"),
    }


def get_state_from_location(
    location: Union[LocationInfo, dict, str], state_code: bool = False
) -> Union[str, None]:
    """
    Given a location (LocationInfo, dict, or string), return the state name or state code using Mapbox geocoding.
    If a string is provided, geocode to get lat/lng, then reverse geocode to get state.
    If state_code=True, returns the state code (e.g., 'KA'), else returns the state name (e.g., 'Karnataka').
    Handles region extraction from both features and context.
    """
    if isinstance(location, str):
        normalized_query = _normalize_query(location)
        use_cache = len(normalized_query) >= 3
        if use_cache:
            geojson = _cached_forward_geocode(normalized_query, None, None, 1)
            if DEBUG_LRU_CACHE:
                log_lru_cache("forward", _cached_forward_geocode)
        else:
            geojson = _forward_geocode(location, {"limit": 1})

        if not geojson or "features" not in geojson:
            print(f"Mapbox returned invalid response for location: {location}")
            return None

        features = geojson.get("features", [])
        if features and "center" in features[0]:
            lng, lat = features[0]["center"]
        else:
            print(f"No geocoding result for: {location}")
            return None
    else:
        lat = getattr(location, "lat", None) or location.get("lat")
        lng = getattr(location, "lng", None) or location.get("lng")
        if lat is None or lng is None:
            print(f"No lat/lng in location: {location}")
            return None
    # Reverse geocode to get state
    geojson = _cached_reverse_geocode(lat, lng)
    if DEBUG_LRU_CACHE:
        log_lru_cache("reverse", _cached_reverse_geocode)
    if not geojson or "features" not in geojson:
        print(f"Mapbox returned invalid response for reverse geocoding: {lat}, {lng}")
        return None
    features = geojson.get("features", [])
    # Try to find a feature of type 'region'
    for feature in features:
        if "region" in feature.get("place_type", []):
            if state_code:
                # Try to get short_code (e.g., 'IN-KA') and extract last part
                short_code = feature.get("properties", {}).get("short_code")
                if short_code and "-" in short_code:
                    return short_code.split("-")[-1].upper()
                # Fallback: try context
                for ctx in feature.get("context", []):
                    if ctx.get("id", "").startswith("region"):
                        sc = ctx.get("short_code")
                        if sc and "-" in sc:
                            return sc.split("-")[-1].upper()
                # Fallback: return None
                return None
            else:
                return feature.get("text")
        # Check context for region
        for ctx in feature.get("context", []):
            if ctx.get("id", "").startswith("region"):
                if state_code:
                    sc = ctx.get("short_code")
                    if sc and "-" in sc:
                        return sc.split("-")[-1].upper()
                    return None
                else:
                    return ctx.get("text")
    print(f"No region found in reverse geocode for: {location}, features: {features}")
    return None


def get_distance_km(
    origin: Union[LocationInfo, dict, str], destination: Union[LocationInfo, dict, str]
) -> float:
    """
    Given two locations (LocationInfo, dict, or string), return the driving distance in kilometers using Mapbox Directions API.
    If a string is provided, geocode to get lat/lng first.
    Uses the correct Mapbox profile.
    """

    def get_lat_lng(loc):
        if isinstance(loc, str):
            normalized_query = _normalize_query(loc)
            use_cache = len(normalized_query) >= 3
            if use_cache:
                geojson = _cached_forward_geocode(normalized_query, None, None, 1)
                if DEBUG_LRU_CACHE:
                    log_lru_cache("forward", _cached_forward_geocode)
            else:
                geojson = _forward_geocode(loc, {"limit": 1})
            if not geojson or "features" not in geojson:
                print(f"Mapbox returned invalid response for location: {loc}")
                return None, None

            features = geojson.get("features", [])
            if features and "center" in features[0]:
                lng, lat = features[0]["center"]
                return lat, lng
            else:
                print(f"No geocoding result for: {loc}")
                return None, None
        lat = getattr(loc, "lat", None) or loc.get("lat")
        lng = getattr(loc, "lng", None) or loc.get("lng")
        return lat, lng

    o_lat, o_lng = get_lat_lng(origin)
    d_lat, d_lng = get_lat_lng(destination)
    if None in (o_lat, o_lng, d_lat, d_lng):
        print(f"Invalid coordinates: {o_lat}, {o_lng}, {d_lat}, {d_lng}")
        return None
    data = _cached_directions(
        round(o_lng, 4),
        round(o_lat, 4),
        round(d_lng, 4),
        round(d_lat, 4),
    )
    if DEBUG_LRU_CACHE:
        log_lru_cache("directions", _cached_directions)
    routes = data.get("routes", [])
    if not routes:
        print(f"No routes found in directions response: {data}")
        return None
    try:
        meters = routes[0]["distance"]
        return round(meters / 1000.0, 2)
    except (KeyError, IndexError, TypeError) as e:
        print(f"Error extracting distance from response: {e}, data: {data}")
        return None


def _extract_geography_from_context(feature: dict) -> dict:
    """
    Extract country, state, region codes and names from Mapbox feature context.

    Mapbox context structure:
    - country: id="country.xxx", short_code="in", text="India"
    - region (state): id="region.xxx", short_code="IN-KA", text="Karnataka"
    - place (city): id="place.xxx", text="Bengaluru"
    - postcode: id="postcode.xxx", text="560001"

    Returns:
        dict with country, country_code, state, state_code, region, region_code, postal_code
    """
    geography = {
        "country": None,
        "country_code": None,
        "state": None,
        "state_code": None,
        "region": None,
        "region_code": None,
        "postal_code": None,
    }

    # Get context array from feature
    context = feature.get("context", [])

    # Extract from context
    for ctx in context:

        ctx_id = ctx.get("id", "")

        # Country
        if ctx_id.startswith("country"):
            geography["country"] = ctx.get("text")
            geography["country_code"] = ctx.get("short_code", "").upper()

        # Region/State
        elif ctx_id.startswith("region"):
            geography["state"] = ctx.get("text")
            # short_code format: "IN-KA" -> extract "KA"
            short_code = ctx.get("short_code", "")
            if short_code and "-" in short_code:
                geography["state_code"] = short_code.split("-")[-1].upper()

        # Place (city/locality) - use as region
        elif ctx_id.startswith("place"):
            geography["region"] = ctx.get("text")
            # Generate region code from text (first 3 letters uppercase)
            # or use wikidata if available
            text = ctx.get("text", "")
            if text:
                geography["region_code"] = text[:3].upper().replace(" ", "")

        # Postal code
        elif ctx_id.startswith("postcode"):
            geography["postal_code"] = ctx.get("text")

    # Also check feature's own properties for place_type
    place_types = feature.get("place_type", [])

    # If the feature itself is a place (city), use it as region
    if "place" in place_types:
        geography["region"] = feature.get("text")
        if feature.get("text"):
            geography["region_code"] = feature.get("text")[:3].upper().replace(" ", "")

    # If feature is a region (state), use it
    if "region" in place_types:
        geography["state"] = feature.get("text")
        # Try to get short_code from properties
        short_code = feature.get("properties", {}).get("short_code", "")
        if short_code and "-" in short_code:
            geography["state_code"] = short_code.split("-")[-1].upper()

    # If feature is a country, use it
    if "country" in place_types:
        geography["country"] = feature.get("text")
        geography["country_code"] = (
            feature.get("properties", {}).get("short_code", "").upper()
        )

    return geography


def _score_location(
    feature,
    query,
    user_state_code: str = None,
    user_region_code: str = None,
    airport_place_names:set=None,
):
    score = 0

    name = feature.get("place_name", "").lower() #E.g, "Kempegowda International Airport, Bengaluru, Karnataka, India"
    query = query.lower()
    place_types = feature.get("place_type", [])
    relevance = feature.get("relevance", 0)

    geography = _extract_geography_from_context(feature)

    # -------------------------
    # 1. TEXT MATCH
    # -------------------------
    if query in name:
        score += 50

    if name.startswith(query):
        score += 30

    # -------------------------
    # 2. AIRPORT INTENT
    # -------------------------
    if "airport" in query:
        if "airport" in name:
            score += 100
        if "international airport" in name:
            score += 150

    # -------------------------
    # 3. DOMAIN BOOST
    # -------------------------
    if airport_place_names and len(airport_place_names) > 0:
        if any(ap.lower() in name for ap in airport_place_names):
            score += 300

    # -------------------------
    # 4. PLACE TYPE
    # -------------------------
    if "poi" in place_types:
        score += 40
    elif "place" in place_types:
        score += 20
    elif "address" in place_types:
        score -= 10

    # -------------------------
    # 5. REGION MATCH (STRONGEST GEO)
    # -------------------------
    geo_region_code = geography.get("region_code", None)
    if geo_region_code and user_region_code:
        if geo_region_code.lower() == user_region_code.lower():
            score += 150

    # -------------------------
    # 6. STATE MATCH
    # -------------------------
    geo_state_code = geography.get("state_code", None)

    if geo_state_code and user_state_code:
        if geo_state_code.lower() == user_state_code.lower():
            score += 80

    # -------------------------
    # 7. MAPBOX RELEVANCE
    # -------------------------
    score += relevance * 10

    return score, geography


def get_location_suggestions(
    query: str,
    allowed_countries: Optional[List[str]] = ["IN"],
    limit: int = 5,
    proximity: Optional[LocationProximity] = None,
) -> list[LocationInfo]:
    """

    Given a partial location string, return a list of enriched LocationInfo objects using Mapbox geocoding, with improved ranking based on text match,
    place type, and proximity.

    Args:
        query: Search query string
        country_filter: List of ISO country codes to filter results (default ["IN"] for India as we are India-focused so far, hence suggest only Indian locations)
        limit: Maximum number of results to return
        proximity: Optional LocationProximity object to bias results towards a specific lat/lng

    Returns:
        List of LocationInfo objects with geography data populated, ranked by relevance and proximity
    """
    normalized_query = _normalize_query(query)
    if len(normalized_query) <= 1:
        print(f"Query too short for geocoding: '{query}'")
        return []

    user_state_code = None
    user_region_code = None

    if (
        proximity
    ):  # User proximity(lon/lat info) is the strongest signal for ranking, so we extract geography from it to use in scoring
        geo = get_geography_from_coordinates_cached(
            round(proximity.lat, 2),
            round(proximity.lng, 2),
        )
        user_state_code = geo.get("state_code", None)
        user_region_code = geo.get("region_code", None)

    use_cache = len(normalized_query) >= 3
    if use_cache:
        country_key = (
            ",".join(allowed_countries or []).lower() if allowed_countries else None
        )
        prox_key = None
        if proximity:
            prox_key = f"{round(proximity.lng,2)},{round(proximity.lat,2)}"

        # Parameters that affect the cache key must be passed as separate arguments to the cached function, not inside a dict
        geojson = _cached_forward_geocode(
            normalized_query, country_key, prox_key, limit
        )

        if DEBUG_LRU_CACHE:
            log_lru_cache("forward", _cached_forward_geocode)
    else:
        params = {
            "limit": limit,
            "country": (
                [code.lower() for code in allowed_countries]
                if allowed_countries
                else None
            ),  # Must be a list of lowercase codes
        }
        if proximity:
            params["proximity"] = f"{proximity.lng},{proximity.lat}"
        # Pop nones from params
        params = {k: v for k, v in params.items() if v is not None}
        geojson = _forward_geocode(query, params)

    if not geojson or "features" not in geojson:
        print(f"Mapbox returned invalid response for query: {query}")
        return []

    features = geojson.get("features", [])
    # Step 1: Score geographical features
    scored_items: List[dict] = []
    
    
    airport_features= _get_airport_features(query)
    for feature in features:
        score, geography = _score_location(
            feature,
            query=query,
            user_state_code=user_state_code,
            user_region_code=user_region_code,
            airport_place_names={af["place_names"] for af in airport_features}
        )
        scored_items.append(
            {
                "score": score,
                "feature": feature,
                "geography": geography,
            }
        )
    # Step 2: Sort descending
    scored_items.sort(key=lambda x: x["score"], reverse=True)

    suggestions = []

    for item in scored_items:

        feature = item["feature"]
        geography = item["geography"]

        display_name = feature.get("place_name")
        coords = feature.get("center", [None, None])
        lng, lat = coords if len(coords) == 2 else (None, None)
        place_id = feature.get("id")

        try:
            location = LocationInfo(
                display_name=display_name,
                lat=lat,
                lng=lng,
                place_id=place_id,
                address=display_name,
                country=geography["country"],
                country_code=geography["country_code"],
                state=geography["state"],
                state_code=geography["state_code"],
                region=geography["region"],
                region_code=geography["region_code"],
                postal_code=geography["postal_code"],
            )
        except:
            location = LocationInfo(
                display_name=display_name,
                lat=lat,
                lng=lng,
                place_id=place_id,
                address=display_name,
            )

        suggestions.append(location)

    return suggestions


def get_location_from_coordinates(lat: float, lng: float) -> Optional[LocationInfo]:
    """
    Given latitude and longitude, return the corresponding location details using Mapbox reverse geocoding.
    The returned LocationInfo includes display_name, lat, lng, place_id, address, and geography fields.

    Args:
        lat: Latitude of the location
        lng: Longitude of the location
    Returns:
        LocationInfo object with location details, or None if not found
    """

    geojson = _cached_reverse_geocode(lat, lng)
    if DEBUG_LRU_CACHE:
        log_lru_cache("reverse", _cached_reverse_geocode)

    if not geojson or "features" not in geojson:
        print(f"Mapbox returned invalid response for coordinates: {lat}, {lng}")
        return None

    features = geojson.get("features", [])
    if not features:
        print(f"No reverse geocoding result for coordinates: {lat}, {lng}")
        return None

    feature = features[0]  # Take the most relevant feature
    display_name = feature.get("place_name")
    place_id = feature.get("id")

    # Extract geography from context
    geography = _extract_geography_from_context(feature)

    try:
        location_info = LocationInfo(
            display_name=display_name,
            lat=lat,
            lng=lng,
            place_id=place_id,
            address=display_name,
            country=geography["country"],
            country_code=geography["country_code"],
            state=geography["state"],
            state_code=geography["state_code"],
            region=geography["region"],
            region_code=geography["region_code"],
            postal_code=geography["postal_code"],
        )
        return location_info
    except Exception as e:
        print(f"Error creating LocationInfo from reverse geocode: {e}")
        return LocationInfo(
            display_name=display_name,
            lat=lat,
            lng=lng,
            place_id=place_id,
            address=display_name,
        )


#if __name__ == "__main__":
    # Test location suggestions
    # test_query = "Giri Nivas 6th Cross, Rifco Shanthiniketan Layout, Bengaluru 560049"
    # suggestions = get_location_suggestions(test_query, allowed_countries=["IN"], proximity=LocationProximity(lat=12.9716, lng=77.5946))
    # for loc in suggestions:
    #     print(loc)


# Get location from coordinates
# lat, lng = 12.2958, 76.6394
# location = get_location_from_coordinates(lat, lng)
# print(location)

# Get distance between two locations
# origin = LocationInfo(
#     display_name="Bengaluru",
#     place_id="place.123",
#     address="Bengaluru, Karnataka, India",
#     lat=12.9716,
#     lng=77.5946,
# )
# destination = LocationInfo(
#     display_name="Mysuru",
#     place_id="place.456",
#     address="Mysuru, Karnataka, India",
#     lat=12.2958,
#     lng=76.6394,
# )
# distance = get_distance_km(origin, destination)
# print(f"Distance between {origin} and {destination}: {distance} km")
# Get state from location
# location = LocationInfo(
#     display_name="Bengaluru, Karnataka, India",
#     place_id="place.123",
#     address="Bengaluru, Karnataka, India",
#     lat=12.9716,
#     lng=77.5946,)
# state = get_state_from_location(location, state_code=True)
# print(f"State code for {location.display_name}: {state}")
# Get geography from coordinates
# lat, lng = 12.9716, 77.5946
# geography = get_geography_from_coordinates(lat, lng)
# print(f"Geography for coordinates ({lat}, {lng}): {geography}")
