from typing import Optional
from core.store import ConfigStore
from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema
from models.map.location_schema import LocationInfo
from services.geography_service import (
    lookup_country_by_country_id,
    lookup_region_by_code,
    lookup_state_by_code,
    look_up_state_by_id,
)


def get_region_from_location(
    location: LocationInfo, config_store: ConfigStore
) -> Optional[RegionSchema]:
    """
    Given a location (with region_code), find and return the matching region object
    from config_store.geographies.regions, checking both region_code and alt_region_codes.
    """

    region_code = location.region_code
    if not region_code:
        return None
    region_code = region_code.upper()
    region = lookup_region_by_code(config_store.geographies.regions, region_code)
    # Enrich region with state info from config_store.geographies.states because a region belongs to a state
    if region:
        _enrich_region_with_state_and_country(region, config_store)

    
    return region


def _enrich_region_with_state_and_country(
    region: RegionSchema, config_store: ConfigStore
):
    state_id = region.state_id
    if state_id and config_store.geographies.states:
        state_info = look_up_state_by_id(config_store.geographies.states, state_id)
        if state_info:
            region.state_code = state_info.state_code
            region.state_name = state_info.state_name
            # Enrich region with country info from config_store.geographies.countries because a state belongs to a country
            country_id = state_info.country_id

            if country_id and config_store.geographies.countries:
                country_info = lookup_country_by_country_id(
                    config_store.geographies.countries, country_id
                )
                if country_info:
                    region.country_code = country_info.country_code
                    region.country_name = country_info.country_name


def _enrich_state_with_country(state: StateSchema, config_store: ConfigStore):
    country_id = state.country_id
    if country_id and config_store.geographies.countries:
        country_info = lookup_country_by_country_id(
            config_store.geographies.countries, country_id
        )
        if country_info:
            state.country_code = country_info.country_code
            state.country_name = country_info.country_name
           


def get_state_from_location_v2(
    location: LocationInfo, config_store: ConfigStore
) -> Optional[StateSchema]:
    """
    Given a location (with state_code), find and return the matching state name
    from config_store.geographies.states.
    """

    state_code = location.state_code
    if not state_code:
        return None
    state_code = state_code.upper()
    state = lookup_state_by_code(
        states=config_store.geographies.states, state_code=state_code
    )
    # Enrich state with country info from config_store.geographies.countries because a state belongs to a country
    if state:
        _enrich_state_with_country(state, config_store)

    return state
