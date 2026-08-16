# Add trip type

from typing import Optional
from core.exceptions import GENERIC_EXCEPTION, SAME_PICKUP_DROPOFF_LOCATION, TRIP_PACKAGE_FETCH_FAILED, CabboException
from core.security import RoleEnum
from core.store import ConfigStore
from models.map.location_schema import LocationInfo, MobilityHub
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import TripTypeMaster
from models.trip.trip_schema import TripClassificationResult, TripTypeSchema, TripTypeUpdateSchema
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from services.location_service import get_distance_km_haversine
from services.trips.local_hourly_rental_service import get_hourly_rental_max_included_km
from services.trips.outstation_service import get_outstation_min_outbound_distance
from core.config import settings

_MIN_TRIP_DISTANCE_KM = 0.5  # trips shorter than this are rejected as same-location abuse

import logging
log = logging.getLogger(__name__)


async def async_add_trip_type(
    trip_type_data: TripTypeSchema, db: AsyncSession, created_by: RoleEnum= RoleEnum.system
):
    """Asynchronously add a new trip type to the database."""
    try:
        new_trip_type = TripTypeMaster(
            trip_type=trip_type_data.trip_type,
            display_name=trip_type_data.display_name,
            description=trip_type_data.description,
            created_by=created_by,
        )
        db.add(new_trip_type)
        await db.commit()
        await db.refresh(new_trip_type)
        return TripTypeSchema.model_validate(new_trip_type), None
    except Exception as e:
        await db.rollback()
        return None, str(e)

async def async_get_all_trip_types(db: AsyncSession):
    """Asynchronously retrieve all trip types from the database."""
    result = await db.execute(select(TripTypeMaster))
    trip_types = result.scalars().all()
    return [TripTypeSchema.model_validate(trip_type) for trip_type in trip_types]

async def async_update_trip_type(trip_type_data: TripTypeUpdateSchema, db: AsyncSession):
    """Asynchronously update an existing trip type in the database."""
    try:
        result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_data.id))
        trip_type = result.scalar_one_or_none()
        if not trip_type:
            return None, "Trip type not found"
        if trip_type_data.description:
            trip_type.description = trip_type_data.description
        if trip_type_data.display_name:
            trip_type.display_name = trip_type_data.display_name
        if trip_type_data.trip_type:
            trip_type.trip_type = trip_type_data.trip_type

        await db.commit()
        await db.refresh(trip_type)
        return TripTypeSchema.model_validate(trip_type), None
    except Exception as e:
        await db.rollback()
        return None, str(e)
    
async def async_delete_trip_type(trip_type_id: str, db: AsyncSession):
    """Asynchronously delete a trip type from the database."""
    try:
        result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_id))
        trip_type = result.scalar_one_or_none()
        if not trip_type:
            return False, "Trip type not found"
        if not trip_type.is_active:
            return False, "Trip type is already inactive"
        trip_type.is_active = False # Soft delete by marking as inactive
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)
    
async def async_activate_trip_type(trip_type_id: str, db: AsyncSession):
    """Asynchronously activate a trip type in the database."""
    try:
        result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_id))
        trip_type = result.scalar_one_or_none()
        if not trip_type:
            return False, "Trip type not found"
        if trip_type.is_active:
            return False, "Trip type is already active"
        trip_type.is_active = True
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        return False, str(e)
    
async def async_get_trip_type_by_id(trip_type_id: str, db: AsyncSession):
    """Asynchronously retrieve a trip type by its ID from the database."""
    result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.id == trip_type_id))
    trip_type = result.scalar_one_or_none()
    if trip_type:
        return TripTypeSchema.model_validate(trip_type)
    return None

async def async_get_trip_type_by_name(trip_type_name: TripTypeEnum, db: AsyncSession):
    """Asynchronously retrieve a trip type by its name from the database."""
    result = await db.execute(select(TripTypeMaster).where(TripTypeMaster.trip_type == trip_type_name))
    trip_type = result.scalar_one_or_none()
    if trip_type:
        return TripTypeSchema.model_validate(trip_type)
    return None


def classify_trip_type(
    pickup: LocationInfo,
    dropoff: Optional[LocationInfo],
    config_store: ConfigStore = None,
) -> TripClassificationResult:
    # Rule 1: No dropoff → local (hourly rental, no fixed destination)
    if not dropoff:
        # Not checking if airport pickup here, as customer can want a rental without a fixed destination that happens to be at an airport (e.g. "rent a car for the day, I'll decide where to go later"). 
        return TripClassificationResult(TripTypeEnum.local, None, False)

    # Guard: reject same-location trips (abuse prevention)
    # Fast path — same place_id means identical location, no math needed.
    if pickup.place_id and dropoff.place_id and pickup.place_id == dropoff.place_id:
        raise CabboException(
            "Pickup and dropoff cannot be the same location.",
            status_code=400,
            error_code=SAME_PICKUP_DROPOFF_LOCATION,
        )
    # Slow path — different place_ids but coordinates are effectively the same.
    outbound_distance = get_distance_km_haversine(origin=pickup, destination=dropoff)
    log.debug(f"Calculated outbound distance excluding hop legs, return legs and real tortuosity: {outbound_distance} km")
    
    if outbound_distance is not None and outbound_distance < _MIN_TRIP_DISTANCE_KM:
        raise CabboException(
            "Pickup and dropoff are too close to each other. Please choose locations that are further apart.",
            status_code=400,
            error_code=SAME_PICKUP_DROPOFF_LOCATION,
        )

    if not config_store:
        config_store = settings.get_config_store()

    # Rule 2: Outstation check takes priority over airport mobility_hub.
    # A trip from Bangalore to Mysore Airport is outstation, not airport_drop.
    outstation_min_km = None
    if outbound_distance is not None:
        outstation_min_km = get_outstation_min_outbound_distance(
            pickup=pickup, config_store=config_store
        )
        if outstation_min_km and outbound_distance >= outstation_min_km:
            return TripClassificationResult(TripTypeEnum.outstation, outbound_distance, False)

    # Rule 3: Airport detection via mobility_hub — only evaluated once outstation is ruled out.
    # If distance couldn't be calculated we still honour the airport flag (non-blocking fallback).
    if pickup.mobility_hub == MobilityHub.airport:
        return TripClassificationResult(TripTypeEnum.airport_pickup, outbound_distance, False)
    if dropoff.mobility_hub == MobilityHub.airport:
        return TripClassificationResult(TripTypeEnum.airport_drop, outbound_distance, False)

    # Rule 4: Local classification.
    if outbound_distance is None:
        # Cannot calculate distance and not an airport trip — default to local.
        return TripClassificationResult(TripTypeEnum.local, None, False)

    # Only apply the unclassifiable guard when outstation threshold was unavailable.
    max_included_km = get_hourly_rental_max_included_km(pickup=pickup, config_store=config_store)
    if outstation_min_km is None:
        if not max_included_km or outbound_distance > max_included_km:
            raise CabboException(
                "Unable to classify trip type based on the provided pickup and dropoff locations. Please verify the locations or specify the trip type explicitly.",
                status_code=400,
                error_code=GENERIC_EXCEPTION,
            )

    # has_distance_overage: the trip is local but distance exceeds the region's max included km
    # (e.g. 130 km trip with a 120 km cap — overages will apply; UI should warn the user, this is for cosmetic purposes).
    has_distance_overage = bool(max_included_km and outbound_distance > max_included_km)
    distance_diff_km = outbound_distance - max_included_km if has_distance_overage else None
    return TripClassificationResult(TripTypeEnum.local, outbound_distance, has_distance_overage, distance_diff_km)

def get_packages_by_region_code(trip_type: TripTypeEnum, region_code: str):
    try:
        if trip_type == TripTypeEnum.local:
            # For local trips, we can have region-specific packages based on the region code, which can be a city or district code. This allows us to offer tailored packages for different localities, taking into account factors like traffic patterns, demand, and customer preferences in those areas.
            config_store = settings.get_config_store()
            trip_packages = config_store.local.get(
                region_code
            ).auxiliary_pricing.trip_packages
            return trip_packages if trip_packages else []
        else:
            raise CabboException(
                f"Trip packages are only available for local trips. Trip type {trip_type} is not supported for trip packages.",
                status_code=400,
                error_code=TRIP_PACKAGE_FETCH_FAILED,
            )
    except Exception as e:
        raise CabboException(
            f"Error fetching trip packages for region code {region_code}",
            status_code=500,
            error_code=TRIP_PACKAGE_FETCH_FAILED,
        )

def serialize_trip_type(trip_type_master, trip_dict: dict):
        trip_type_data = TripTypeSchema.model_validate(
            trip_type_master
        ).model_dump()
        trip_dict["trip_type"] = trip_type_data
        trip_dict.pop("trip_type_id", None)
        trip_dict.pop("trip_type_master", None)
        return trip_dict

def remove_extra_fields_from_trip_type(trip_type: dict):
    keys_to_remove = ["id"]
    for key in keys_to_remove:
        trip_type.pop(key, None)
    return trip_type