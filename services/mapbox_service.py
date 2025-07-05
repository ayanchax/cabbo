from typing import Union
from mapbox import Geocoder, Directions
from models.geography.geo_enums import LocationInfo
from core.config import settings

MAPBOX_TOKEN = settings.MAPBOX_TOKEN


def get_state_from_location(location: Union[LocationInfo, dict, str], state_code: bool = False) -> str:
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


def get_location_suggestions(query: str):
    """
    Given a partial location string, return a list of LocationInfo objects using Mapbox geocoding.
    """
    geocoder = Geocoder(access_token=MAPBOX_TOKEN)
    resp = geocoder.forward(query, limit=5)
    geojson = resp.geojson()
    features = geojson.get("features", [])
    suggestions = []
    for feature in features:
        display_name = feature.get("place_name")
        coords = feature.get("center", [None, None])
        lng, lat = coords if len(coords) == 2 else (None, None)
        place_id = feature.get("id")
        suggestions.append(
            LocationInfo(
                display_name=display_name,
                lat=lat,
                lng=lng,
                place_id=place_id,
                address=display_name,
            )
        )
    return suggestions
