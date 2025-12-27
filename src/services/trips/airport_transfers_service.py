from core.store import ConfigStore


def get_airport_pickup_pricing_configuration_by_region(
    region_code: str, config_store: ConfigStore
):
    """
    Retrieves airport pickup pricing configuration for a specific region code from the configuration store.
    Args:
        region_code (str): The region code to look up.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        MasterPricingConfiguration: Airport pickup pricing configuration for the specified region code.
    """
    if not config_store:
        return None
    if not config_store.is_cache_valid():
        config_store.warm_up_cache()
    region_code = region_code.upper()
    # Find the airport pickup configuration for the given region code
    return config_store.airport_pickup.get(region_code, None)


def get_airport_dropoff_pricing_configuration_by_region(
    region_code: str, config_store: ConfigStore
):
    """
    Retrieves airport dropoff pricing configuration for a specific region code from the configuration store.
    Args:
        region_code (str): The region code to look up.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        MasterPricingConfiguration: Airport dropoff pricing configuration for the specified region code.
    """
    if not config_store:
        return None
    if not config_store.is_cache_valid():
        config_store.warm_up_cache()
    region_code = region_code.upper()
    # Find the airport dropoff configuration for the given region code
    return config_store.airport_drop.get(region_code, None)
