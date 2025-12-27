
from core.store import ConfigStore


def get_allowed_outstation_states(config_store: ConfigStore) -> set:
    """
    Returns a set of state codes that are allowed for outstation trips.
    """
    if not config_store:
        return set()
    if not config_store.is_cache_valid():
        config_store.warm_up_cache()
        
    allowed_states = set()
    for state_code, _ in config_store.outstation.items():
        allowed_states.add(state_code.upper())
    return allowed_states