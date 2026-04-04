import sys
from pathlib import Path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from typing import List, Optional, Union
from mapbox import Geocoder, Directions
from models.map.location_schema import LocationInfo
from core.config import settings

MAPBOX_TOKEN = settings.MAPBOX_TOKEN


def get_state_from_location(
    location: Union[LocationInfo, dict, str], state_code: bool = False
) -> Union[str, None]:
    """
    Given a location (LocationInfo, dict, or string), return the state name or state code using Mapbox geocoding.
    If a string is provided, geocode to get lat/lng, then reverse geocode to get state.
    If state_code=True, returns the state code (e.g., 'KA'), else returns the state name (e.g., 'Karnataka').
    Handles region extraction from both features and context.
    """
    geocoder = Geocoder(access_token=MAPBOX_TOKEN)
    if isinstance(location, str):
        resp = geocoder.forward(location, limit=1)
        geojson = resp.geojson()
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
    resp = geocoder.reverse(lon=lng, lat=lat)
    geojson = resp.geojson()
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
    directions = Directions(access_token=MAPBOX_TOKEN)
    geocoder = Geocoder(access_token=MAPBOX_TOKEN)

    def get_lat_lng(loc):
        if isinstance(loc, str):
            resp = geocoder.forward(loc, limit=1)
            geojson = resp.geojson()
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
    coords = [(o_lng, o_lat), (d_lng, d_lat)]
    resp = directions.directions(coords, profile="mapbox/driving")
    data = resp.geojson()
    if "features" not in data or not data["features"]:
        print(f"No route features found in directions response: {data}")
        return None
    try:
        meters = data["features"][0]["properties"]["distance"]
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


def get_location_suggestions(
    query: str, country_filter: Optional[List[str]] = ["IN"], limit: int = 5
) -> list[LocationInfo]:
    """
    Given a partial location string, return a list of enriched LocationInfo objects using Mapbox geocoding.

    Args:
        query: Search query string
        country_filter: List of ISO country codes to filter results (default ["IN"] for India as we are India-focused so far, hence suggest only Indian locations)
        limit: Maximum number of results to return

    Returns:
        List of LocationInfo objects with geography data populated
    """
    geocoder = Geocoder(access_token=MAPBOX_TOKEN)

    # Add country filter to limit results
    params = {
        "limit": limit,
    }
    if country_filter:
        # ✅ Fix: Don't use .lower() - Mapbox expects the full lowercase ISO code
        params["country"] = [code.lower() for code in country_filter]  # Must be a list

    resp = geocoder.forward(query, **params)
    geojson = resp.geojson()
    features = geojson.get("features", [])

    suggestions = []
    for feature in features:
        display_name = feature.get("place_name")
        coords = feature.get("center", [None, None])
        lng, lat = coords if len(coords) == 2 else (None, None)
        place_id = feature.get("id")

        # Extract geography from context
        geography = _extract_geography_from_context(feature)
        try:
            # Create enriched LocationInfo
            location = LocationInfo(
                display_name=display_name,
                lat=lat,
                lng=lng,
                place_id=place_id,
                address=display_name,
                # Add geography fields
                country=geography["country"],
                country_code=geography["country_code"],
                state=geography["state"],
                state_code=geography["state_code"],
                region=geography["region"],
                region_code=geography["region_code"],
                postal_code=geography["postal_code"],
            )
        except Exception as e:
            print(f"Error creating enriched LocationInfo: {e}")
            location = LocationInfo(
                display_name=display_name,
                lat=lat,
                lng=lng,
                place_id=place_id,
                address=display_name,
            )

        suggestions.append(location)

    return suggestions

# if __name__ == "__main__":
#     # Test location suggestions
#     test_query = "mysore palace"
#     suggestions = get_location_suggestions(test_query)
#     for loc in suggestions:
#         print(loc)

