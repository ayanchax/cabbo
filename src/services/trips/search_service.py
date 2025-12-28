from core.exceptions import CabboException
from core.store import ConfigStore
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_schema import TripSearchRequest, TripSearchResponse
from sqlalchemy.orm import Session
from services.trips.trip_service import validate_trip_search
from services.trips.airport_transfers_service import (
    get_airport_dropoff_trip_options,
    get_airport_pickup_trip_options,
)
from services.trips.local_hourly_rental_service import (
    get_local_trip_options,
)
from services.trips.outstation_service import (
    get_outstation_trip_options,
)
from core.config import settings


def search(
    search_in: TripSearchRequest, requestor: str, db: Session
) -> TripSearchResponse:
    config_store: ConfigStore = settings.CONFIG_STORE
    
    validate_trip_search(
        search_in=search_in, requestor=requestor, db=db, config_store=config_store
    )
    trip_type = search_in.trip_type
    if trip_type == TripTypeEnum.local:
        # Retrieve local trip pricing configuration for the origin region
        return get_local_trip_options(search_in=search_in, config_store=config_store)

    if trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        if trip_type == TripTypeEnum.airport_pickup:
            return get_airport_pickup_trip_options(
                search_in=search_in, config_store=config_store
            )
        elif trip_type == TripTypeEnum.airport_drop:
            return get_airport_dropoff_trip_options(
                search_in=search_in, config_store=config_store
            )
    elif trip_type == TripTypeEnum.outstation:
        return get_outstation_trip_options(
            search_in=search_in, config_store=config_store
        )

    else:
        raise CabboException(f"Trip type {trip_type} is not supported", status_code=501)
