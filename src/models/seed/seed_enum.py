from enum import Enum


class SeedKeyEnum(str, Enum):
    INITIAL_SEED_COMPLETED = "initial_seed_completed"

    # Master data seeding keys
    SEED_MASTER_DATA_V1 ="seed.master.data.v1"

    # Geo seeding keys
    SEED_GEO_CORE_V1 = "seed.geo.core.v1"
    SEED_GEO_REGIONS_V1 = "seed.geo.regions.v1"

    # Pricing seeding keys
    SEED_PRICING_LOCAL_V1="seed.pricing.local.v1"
    SEED_PRICING_OUTSTATION_V1="seed.pricing.outstation.v1"
    SEED_PRICING_AIRPORT_V1="seed.pricing.airport.v1"
    SEED_PRICING_PLATFORM_V1="seed.pricing.platform.v1"
    SEED_PRICING_NIGHT_V1="seed.pricing.night.v1"
    SEED_PRICING_PERMIT_V1="seed.pricing.permit.v1"
    SEED_PRICING_CANCELLATION_POLICY_V1="seed.pricing.cancellation.policy.v1"


