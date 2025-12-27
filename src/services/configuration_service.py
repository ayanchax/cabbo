from typing import Optional
from core.store import ConfigStore
from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema
from models.map.location_schema import LocationInfo
from services.geography_service import lookup_region_by_code, lookup_state_by_code


def get_region_from_location(
    location: LocationInfo, config_store: ConfigStore
) -> Optional[RegionSchema]:
    """
    Given a location (with region_code), find and return the matching region object
    from config_store.geographies.regions, checking both region_code and alt_region_codes.
    """
    if not config_store:
        return None

    if not config_store.is_cache_valid():
        config_store.warm_up_cache()

    region_code = location.region_code
    if not region_code:
        return None
    region_code = region_code.upper()
    return lookup_region_by_code(config_store.geographies.regions, region_code)


def get_state_from_location_v2(
    location: LocationInfo, config_store: ConfigStore
) -> Optional[StateSchema]:
    """
    Given a location (with state_code), find and return the matching state name
    from config_store.geographies.states.
    """
    if not config_store:
        return None
    if not config_store.is_cache_valid():
        config_store.warm_up_cache()
    state_code = location.state_code
    if not state_code:
        return None
    state_code = state_code.upper()
    return lookup_state_by_code(
        states=config_store.geographies.states, state_code=state_code
    )
