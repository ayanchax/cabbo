from typing import Optional
from customer_api.src.core.store import ConfigStore
from customer_api.src.db.database import get_mysql_local_session
from customer_api.src.models.geography.region_schema import RegionSchema
from customer_api.src.models.geography.state_schema import StateSchema
from customer_api.src.models.map.location_schema import LocationInfo
from customer_api.src.models.pricing.pricing_schema import Currency
from customer_api.src.services.geography_service import (
    lookup_country_by_country_id,
    lookup_region_by_code,
    lookup_state_by_code,
    look_up_state_by_id,
)
from sqlalchemy.orm import Session
from customer_api.src.core.config import settings


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

def get_all_cabs(db: Session):
    config_store: ConfigStore = settings.get_config_store(db)
    cabs = config_store.cabs
    return cabs

def get_currency(db: Session):
    config_store: ConfigStore = settings.get_config_store(db)
    currency: Currency = Currency(
        code=config_store.geographies.country_server.currency or "INR",
        symbol=config_store.geographies.country_server.currency_symbol or "₹",
        decimal_places=config_store.geographies.country_server.currency_decimal_places
        or 2,
        in_words=config_store.geographies.country_server.currency_in_words or "Rupees",
        international_name=config_store.geographies.country_server.currency_international_name
        or "Indian Rupee",
        symbol_position=config_store.geographies.country_server.currency_symbol_position
        or "before",
        code_position=config_store.geographies.country_server.currency_code_position
        or "after",
        thousand_separator=config_store.geographies.country_server.currency_thousand_separator
        or ",",
        decimal_separator=config_store.geographies.country_server.currency_decimal_separator
        or ".",
        lowest_unit_name=config_store.geographies.country_server.currency_lowest_unit_name
        or "Paise",
        lowest_unit_conversion_factor=config_store.geographies.country_server.currency_lowest_unit_conversion_factor
        or 100,
    )
    return currency

def serialize_currency(trip_dict: dict, db: Session=None):
    if not db:
        db = get_mysql_local_session()
    currency= get_currency(db)
    trip_dict["currency"] = currency.model_dump() if currency else None
    return trip_dict

def remove_extra_fields_from_currency(currency: dict):
    keys_to_remove = ["code_position", "decimal_places", "decimal_separator", "in_words","international_name","symbol_position","thousand_separator"]
    for key in keys_to_remove:
                    currency.pop(key, None)
    return currency

