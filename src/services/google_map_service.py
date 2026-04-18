# We are not using Google Maps for our maps provider, if need be, in the future, we might shift to Google Maps
# Placeholder for Google Maps API calls
from typing import Union
from models.map.location_schema import LocationInfo


def get_state_from_location(location: Union[LocationInfo, dict, str]):
    pass


def get_distance_km(
    origin: Union[LocationInfo, dict, str], destination: Union[LocationInfo, dict, str]
):
    pass


def get_location_suggestions(query: str):
    pass

def get_location_from_coordinates(lat: float, lng: float):
    pass


