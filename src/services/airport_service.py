from typing import List
from sqlalchemy.orm import Session
from core.constants import APP_NAME
from core.store import ConfigStore
from models.airport.airport_orm import AirportModel
from models.airport.airport_schema import AirportSchema
from models.map.location_schema import LocationInfo
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import Trip
from core.config import settings


SEED_AIRPORTS_DATA = [
    # It can contain multiple airports for a city in a state in a country.
    # Admin can add more airports for a city/region inside a (state, country) via admin panel if needed.
    # Admin can also add more regions/cities under a (state, country) via admin panel if needed.
    {
        "display_name": "Kempegowda International Airport, Bengaluru",
        "lat": 13.1986,
        "lng": 77.7066,
        "place_id": "ChIJL_P_CXMEDTkRw0ZdG-0GVvw",  # official Mapbox place ID for the airport in Bengaluru
        "address": "Kempegowda International Airport, Devanahalli, Bengaluru, Karnataka 560300, India",
        "country": "India",
        "country_code": "IN",
        "state": "Karnataka",
        "state_code": "KA",
        "region": "Bangalore",
        "region_code": "BLR",
        "postal_code": "560300",
    },
    {
        "display_name": "Mysore Airport, Mysore",
        "lat": 12.3052,
        "lng": 76.6536,
        "place_id": "ChIJX8f5gq6rDTkR6e-8K5J7hYzA",  # official Mapbox place ID for the airport in Mysore
        "address": "Mysore Airport, Mandakalli, Mysore, Karnataka 570008, India",
        "country": "India",
        "country_code": "IN",
        "state": "Karnataka",
        "state_code": "KA",
        "region": "Mysore",
        "region_code": "MYS",
        "postal_code": "570008",
    },
    {
        "display_name": "Chennai International Airport, Chennai",
        "lat": 12.9941,
        "lng": 80.1709,
        "place_id": "ChIJGZ0fW3KqDTkR6r1K5J7hYzA",  # official Mapbox place ID for the airport in Chennai
        "address": "Chennai International Airport, Tirusulam, Chennai, Tamil Nadu 600027, India",
        "country": "India",
        "country_code": "IN",
        "state": "Tamil Nadu",
        "state_code": "TN",
        "region": "Chennai",
        "region_code": "MAA",
        "postal_code": "600027",
    },
]


def _create_airports(data: List[AirportSchema], session: Session):
    airport_models = []
    for airport in data:
        airport_models.append(
            AirportModel(
                display_name=airport.display_name,
                iata_code=airport.iata_code,
                icao_code=airport.icao_code,
                elevation_ft=airport.elevation_ft,
                timezone=airport.timezone,
                dst=airport.dst,
                tz_database_time_zone=airport.tz_database_time_zone,
                type=airport.type,
                source=airport.source,
                lat=airport.lat,
                lng=airport.lng,
                place_id=airport.place_id,
                address=airport.address,
                country=airport.country,
                country_code=airport.country_code,
                state=airport.state,
                state_code=airport.state_code,
                region=airport.region,
                region_code=airport.region_code,
                postal_code=airport.postal_code,
            )
        )
    session.add_all(airport_models)
    session.commit()
    return [AirportSchema.model_validate(airport) for airport in airport_models]


def create_master_airports_data(session: Session):
    airports_list = [
        AirportSchema.model_validate(airport) for airport in SEED_AIRPORTS_DATA
    ]
    return _create_airports(data=airports_list, session=session)


def get_all_airports(db: Session) -> List[AirportSchema]:
    """Retrieve all airports from the database."""
    airports = db.query(AirportModel).filter(AirportModel.is_serviceable == True).all()
    airport_schemas = [AirportSchema.model_validate(airport) for airport in airports]
    return airport_schemas


def get_airports_in_region(
    airport_locations: List[str], config_store: ConfigStore
) -> List[AirportSchema]:
    airports_in_region: List[AirportSchema] = []
    for loc in airport_locations:
        for airport in config_store.airport_locations:
            if airport.id == loc:
                airports_in_region.append(airport)
    return airports_in_region


def get_airport_by_region_code(
    airports: List[AirportSchema], region_code: str
) -> AirportSchema | None:
    for airport in airports:
        if airport.region_code == region_code:
            return airport #Return the first matching airport
    return None

def get_kwargs_for_airport_transfer(customer_email:str, trip_type:TripTypeEnum, trip:Trip, currency:str ):
    
    app_name = APP_NAME.capitalize()
    app_url = settings.APP_URL

    origin = trip.origin
    validated_origin = LocationInfo.model_validate(origin)
    destination = trip.destination
    validated_destination = LocationInfo.model_validate(destination)