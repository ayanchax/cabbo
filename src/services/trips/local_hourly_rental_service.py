from core.store import ConfigStore


def get_local_trip_pricing_configuration_by_region(region_code:str, config_store: ConfigStore):
    """
    Retrieves configuration settings for a specific region code from the configuration store.
    Args:
        region_code (str): The region code to look up.
        config_store (ConfigStore): The configuration store instance.
    Returns:
        MasterPricingConfiguration: Configuration settings for the specified region code.
    """
    if config_store is None:
        return None
    if not config_store.is_cache_valid():
        config_store.warm_up_cache()
        
    region_code = region_code.upper()
    #Find the local hourly rental configuration for the given region code
    return config_store.local.get(region_code, None)
   