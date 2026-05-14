from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session
from core.security import RoleEnum
from core.store import ConfigStore
from models.airport.airport_orm import AirportModel
from models.airport.airport_schema import AirportSchema, AirportUpdateSchema
from models.map.location_schema import LocationInfo
from services.geography_service import (
    async_get_country_by_id,
    async_get_region_by_code,
    async_get_state_by_id,
)
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from core.config import settings    



SEED_AIRPORTS_DATA_GOOGLE = [
    {
        "display_name": "Kempegowda International Airport Bengaluru",
        "iata_code": "BLR",
        "lat": 13.198909,
        "lng": 77.7068926,
        "place_id": "ChIJZWJEdf4crjsRjkEpoelwbCk",  # Google Maps place ID for BLR airport
        # Address must match what Google Place Details returns for this place_id so the
        # address-heuristic check in validate_initial_serviceable_area passes.
        "address": "Kempegowda International Airport Rd, Devanahalli, Bengaluru, Karnataka 562300, India",
        "country": "India",
        "country_code": "IN",
        "state": "Karnataka",
        "state_code": "KA",
        "region": "Bangalore",
        "region_code": "BLR",
        "postal_code": "562300",  # Devanahalli PIN — not 560300 (Central Bangalore)
        "provider": settings.LOCATION_SERVICE_PROVIDER,
    },
    {
        "display_name": "Mysore Airport",
        "iata_code": "MYQ",
        "lat": 12.2310482,
        "lng": 76.6541862,
        "place_id": "ChIJhVz42G5vrzsRHhC5IHsswy4",  # Google Maps place ID for Mysore airport
        "address": "Airport Rd, Mandakalli, Mysuru, Karnataka 571311, India",
        "country": "India",
        "country_code": "IN",
        "state": "Karnataka",
        "state_code": "KA",
        "region": "Mysore",
        "region_code": "MYS",
        "postal_code": "571311",
        "provider": settings.LOCATION_SERVICE_PROVIDER,
    },
    {
        "display_name": "Chennai International Airport",
        "iata_code": "MAA",
        "lat": 12.9939595,
        "lng": 80.1706653,
        "place_id": "ChIJl2OoXR9eUjoRR27ibiEvCSE",  # Google Maps place ID for Chennai airport
        "address": "Chennai International Airport, Tirusulam, Chennai, Tamil Nadu 600027, India",
        "country": "India",
        "country_code": "IN",
        "state": "Tamil Nadu",
        "state_code": "TN",
        "region": "Chennai",
        "region_code": "MAA",
        "postal_code": "600027",
        "provider": settings.LOCATION_SERVICE_PROVIDER,
    },
]


log = logging.getLogger(__name__)
SEED_AIRPORTS_DATA = SEED_AIRPORTS_DATA_GOOGLE

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
                provider=airport.provider,
            )
        )
    session.add_all(airport_models)
    session.flush()
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
            return airport  # Return the first matching airport
    return None


async def async_add_airport(
    airport_data: AirportSchema, db: AsyncSession, created_by: RoleEnum = RoleEnum.system
) -> tuple[AirportSchema | None, str | None]:
    """Add a new airport to the database."""
    try:
        if not airport_data.region_code:
            return False, "Region code is required to add an airport."

        region_code = airport_data.region_code.upper()
        region = await async_get_region_by_code(
            region_code=region_code, db=db
        )  # Validate if the region exists, will raise exception if not found
        if region is None:
            return (
                False,
                f"Region with code {region_code} not found. Cannot add airport without a valid region.",
            )

        if region.state_id is None:
            return (
                False,
                f"Region with code {region_code} does not have an associated state. Cannot add airport without a valid state.",
            )

        state = await async_get_state_by_id(
            state_id=region.state_id, db=db
        )  # Validate if the state exists, will raise exception if not found
        if state is None:
            return (
                False,
                f"State with id {region.state_id} not found. Cannot add airport without a valid state.",
            )
        if state.country_id is None:
            return (
                False,
                f"State with id {region.state_id} does not have an associated country. Cannot add airport without a valid country.",
            )
        country = await async_get_country_by_id(
            country_id=state.country_id, db=db
        )  # Validate if the country exists, will raise exception if not found
        if country is None:
            return (
                False,
                f"Country with id {state.country_id} not found. Cannot add airport without a valid country.",
            )

        new_airport = AirportModel(
            display_name=airport_data.display_name,
            iata_code=airport_data.iata_code,
            icao_code=airport_data.icao_code,
            elevation_ft=airport_data.elevation_ft,
            timezone=airport_data.timezone,
            dst=airport_data.dst,
            tz_database_time_zone=airport_data.tz_database_time_zone,
            type=airport_data.type,
            source=airport_data.source,
            lat=airport_data.lat,
            lng=airport_data.lng,
            place_id=airport_data.place_id,
            address=airport_data.address,
            country=country.country_name,
            country_code=country.country_code.upper(),
            state=state.state_name,
            state_code=state.state_code.upper(),
            region=region.region_name,
            region_code=region.region_code.upper(),
            postal_code=airport_data.postal_code,
            created_by=created_by,
        )
        db.add(new_airport)
        await db.commit()
        await db.refresh(new_airport)
        return AirportSchema.model_validate(new_airport), None
    except Exception as e:
        await db.rollback()
        log.error(f"Error adding airport: {e}")
        return False, "Failed to add airport due to an internal error."


async def async_get_all_airports_in_state(
    state_code: str, db: AsyncSession
) -> List[AirportSchema]:
    """Get all airports in a specific state."""
    state_code = state_code.upper()
    airports = await db.execute(
        select(AirportModel)
        .filter(
            AirportModel.state_code == state_code, AirportModel.is_serviceable == True
        )
    )
    result = airports.scalars().all()
    return [AirportSchema.model_validate(airport) for airport in result]


async def async_get_all_airports_in_country(
    country_code: str, db: AsyncSession
) -> List[AirportSchema]:
    """Get all airports in a specific country."""
    country_code = country_code.upper()
    airports = await db.execute(
        select(AirportModel)
        .filter(
            AirportModel.country_code == country_code,
            AirportModel.is_serviceable == True,
        )
    )
    result = airports.scalars().all()
    return [AirportSchema.model_validate(airport) for airport in result]


async def async_get_airport_by_region_code(
    region_code: str, db: AsyncSession  ) -> list[AirportSchema] | None:
    """Get all airports in a specific region using the region code."""
    region_code = region_code.upper()
    airports = await db.execute(
        select(AirportModel)
        .filter(
            AirportModel.region_code == region_code,
            AirportModel.is_serviceable == True,
        )
    )
    result = airports.scalars().all()
    if result:
        return [AirportSchema.model_validate(airport) for airport in result]
    return None


async def async_get_all_airports(db: AsyncSession) -> List[AirportSchema]:
    """Retrieve all airports from the database."""
    result = await db.execute(
        select(AirportModel).filter(AirportModel.is_serviceable == True)
    )
    airports = result.scalars().all()
    airport_schemas = [AirportSchema.model_validate(airport) for airport in airports]
    return airport_schemas


async def async_get_airport_by_id(
    airport_id: str, db: AsyncSession
) -> AirportSchema | None:
    """Retrieve an airport by its ID."""
    result = await db.execute(
        select(AirportModel).filter(
            AirportModel.id == airport_id, AirportModel.is_serviceable == True
        )
    )
    airport = result.scalars().first()
    if airport:
        return AirportSchema.model_validate(airport)
    return None


async def async_activate_airport(
    airport_id: str, db: AsyncSession
) -> tuple[bool, str | None]:
    """Activate an airport in the system configuration."""
    try:
        result = await db.execute(
            select(AirportModel).filter(AirportModel.id == airport_id)
        )
        airport = result.scalars().first()
        if airport is None:
            return False, "Airport not found"
        if airport.is_serviceable:
            return False, "Airport is already active."
        
        airport.is_serviceable = True
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        log.error(f"Error activating airport: {e}")
        return False, "Failed to activate airport"


async def async_delete_airport(
    airport_id: str, db: AsyncSession
) -> tuple[bool, str | None]:
    """Delete an airport from the system configuration."""
    try:
        result = await db.execute(
            select(AirportModel).filter(AirportModel.id == airport_id)
        )
        airport = result.scalars().first()
        if airport is None:
            return False, "Airport not found"
        if not airport.is_serviceable:
            return False, "Airport is already inactive."
        airport.is_serviceable = False  # Soft delete by marking as inactive
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        log.error(f"Error deleting airport: {e}")
        return False, "Failed to delete airport"


async def async_update_airport(
    airport_id: str, airport_data: AirportUpdateSchema, db: AsyncSession
) -> tuple[AirportSchema | None, str | None]:
    """Update an existing airport's configuration."""
    try:
        result = await db.execute(
            select(AirportModel).filter(
                AirportModel.id == airport_id, AirportModel.is_serviceable == True
            )
        )
        airport = result.scalars().first()
        if airport is None:
            return None, "Airport not found"

        for field, value in airport_data.model_dump(
            exclude_unset=True, exclude={"id"}
        ).items():
            setattr(airport, field, value)
        await db.commit()
        await db.refresh(airport)
        return AirportSchema.model_validate(airport), None
    except Exception as e:
        await db.rollback()
        log.error(f"Error updating airport: {e}")
        return None, "Failed to update airport"

async def async_get_airport_by_id(airport_id: str, db: AsyncSession) -> AirportSchema | None:
    """Retrieve an airport by its ID."""
    result = await db.execute(
        select(AirportModel).filter(
            AirportModel.id == airport_id, AirportModel.is_serviceable == True
        )
    )
    airport = result.scalars().first()
    if airport:
        return AirportSchema.model_validate(airport)
    return None

def get_all_airports_configuration(
    config_store: ConfigStore
) -> List[AirportSchema]:
    airports: List[AirportSchema] = []
    for airport in config_store.airport_locations:
                if airport.is_serviceable:
                    airports.append(airport)
    return airports

def match_location_to_airport(
    location: LocationInfo,
    airports: List[AirportSchema],
) -> Optional[AirportSchema]:
    """Return the first airport from `airports` that matches `location`.

    Checks in priority order:
      1. place_id  — exact string match (fastest, most reliable)
      2. display_name — case-insensitive prefix in either direction
      3. address  — case-insensitive prefix in either direction
      4. lat/lng  — proximity within ~10 m (0.0001 degree tolerance)
    Returns None when no airport matches.
    """
    if not location or not airports:
        return None

    # 1. place_id exact match
    if location.place_id:
        for airport in airports:
            if airport.place_id and airport.place_id == location.place_id:
                return airport

    # 2. display_name prefix match
    if location.display_name:
        loc_name = location.display_name.lower().strip()
        for airport in airports:
            if airport.display_name:
                apt_name = airport.display_name.lower().strip()
                if loc_name == apt_name or loc_name.startswith(apt_name) or apt_name.startswith(loc_name):
                    return airport

    # 3. address prefix match
    if location.address:
        loc_addr = location.address.lower().strip()
        for airport in airports:
            if airport.address:
                apt_addr = airport.address.lower().strip()
                if loc_addr == apt_addr or loc_addr.startswith(apt_addr) or apt_addr.startswith(loc_addr):
                    return airport

    # 4. lat/lng proximity (~10 m ≈ 0.0001 degree tolerance)
    if location.lat is not None and location.lng is not None:
        for airport in airports:
            if airport.lat is not None and airport.lng is not None:
                if abs(location.lat - airport.lat) <= 0.0001 and abs(location.lng - airport.lng) <= 0.0001:
                    return airport

    return None
