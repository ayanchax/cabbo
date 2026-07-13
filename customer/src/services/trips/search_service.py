from customer_api.src.core.exceptions import TRIP_TYPE_NOT_SUPPORTED, CabboException
from customer_api.src.core.store import ConfigStore
from customer_api.src.models.trip.trip_enums import TripTypeEnum
from customer_api.src.models.trip.trip_schema import TripSearchRequest, TripSearchResponse
from sqlalchemy.orm import Session
from customer_api.src.services.trips.trip_service import validate_trip_search
from customer_api.src.services.trips.airport_transfers_service import (
    get_airport_dropoff_trip_options,
    get_airport_pickup_trip_options,
)
from customer_api.src.services.trips.local_hourly_rental_service import (
    get_local_trip_options,
)
from customer_api.src.services.trips.outstation_service import (
    get_outstation_trip_options,
)
from customer_api.src.core.config import settings


def search(
    search_in: TripSearchRequest, requestor: str, db: Session
) -> TripSearchResponse:
    config_store: ConfigStore = settings.get_config_store(db)

    validate_trip_search(
        search_in=search_in, requestor=requestor, db=db, config_store=config_store
    )
    trip_type = search_in.trip_type
    if trip_type == TripTypeEnum.local:
        # Retrieve local trip pricing configuration for the origin region
        return get_local_trip_options(search_in=search_in, config_store=config_store)

    elif trip_type == TripTypeEnum.airport_pickup:
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
        raise CabboException(f"Trip type {trip_type} is not supported", status_code=501, error_code=TRIP_TYPE_NOT_SUPPORTED)
