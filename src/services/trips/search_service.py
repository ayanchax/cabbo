from core.exceptions import CabboException
from core.store import ConfigStore
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_schema import TripSearchRequest, TripSearchResponse
from sqlalchemy.orm import Session
from services.passenger_service import validate_passenger_id
from services.trip_service import set_default_preferences
from services.trips.airport_transfers_service import get_airport_dropoff_pricing_configuration_by_region, get_airport_pickup_pricing_configuration_by_region
from services.trips.local_hourly_rental_service import get_local_trip_pricing_configuration_by_region
from services.validation_service import validate_serviceable_area
from core.config import settings

config_store:ConfigStore = settings.CONFIG_STORE


def search(search_in: TripSearchRequest, requestor: str, db: Session)->TripSearchResponse:

    #Validate passenger ID if provided
    validate_passenger_id(search_in, requestor, db)

    # Ensure all required trip search preferences have sensible defaults
    set_default_preferences(search_in)

    # Enforce serviceable area boundaries
    validate_serviceable_area(search_in=search_in, config_store=config_store, db=db)

    trip_type = search_in.trip_type
    configuration = None
    # Pricing configuration will be always based on origin region for any type of trip.

    if trip_type == TripTypeEnum.local:
        # Retrieve local trip pricing configuration for the origin region
        configuration = get_local_trip_pricing_configuration_by_region(
            region_code=search_in.origin.region_code, config_store=config_store
        )
    elif trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        if trip_type == TripTypeEnum.airport_pickup:
            # Retrieve airport pickup pricing configuration for the origin region
            configuration = get_airport_pickup_pricing_configuration_by_region(
                region_code=search_in.origin.region_code, config_store=config_store
            )
        elif trip_type == TripTypeEnum.airport_drop:
            # Retrieve airport dropoff pricing configuration for the origin region
            configuration = get_airport_dropoff_pricing_configuration_by_region(
                region_code=search_in.origin.region_code, config_store=config_store
            )
    elif trip_type == TripTypeEnum.outstation:
        # Outstation trip type pricing configuration retrieval can be implemented here
        pass

    else:
        raise CabboException(f"Trip type {trip_type} is not supported", status_code=501)
        

    