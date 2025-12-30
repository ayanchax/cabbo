from datetime import datetime, timezone
import threading
from typing import ClassVar, List, Optional, Union
from pydantic import BaseModel, Field, PrivateAttr
from core.trip_helpers import get_all_trip_types, get_trip_package_configuration_list_by_region_code, get_trip_type_id_by_trip_type
from models.airport.airport_schema import AirportSchema
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.geography.geography_schema import Geographies
from sqlalchemy.orm import Session

from models.pricing.pricing_schema import (
    AirportCabPricingSchema,
    CommonPricingConfigurationSchema,
    FixedPlatformFeeConfigurationSchema,
    LocalCabPricingSchema,
    MasterPricingConfiguration,
    OutstationCabPricingSchema,
)
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_schema import TripTypeSchema
from services.cab_service import get_all_cabs
from services.fuel_service import get_all_fuel_types
from services.geography_service import (
    get_all_countries,
    get_all_regions,
    get_all_states,
    get_all_states,
    get_region_by_id,
    get_state_by_id,
)
from services.pricing_service import (
    get_base_pricings_airport,
    get_base_pricings_local,
    get_base_pricings_outstation,
    get_cancellation_policy_by_region_code,
    get_cancellation_policy_by_state_code,
    get_common_pricing_configurations_by_trip_type_id,
    get_fixed_platform_pricing_configuration,
    get_night_pricing_configuration,
    get_permit_fee_configuration,
)

from core.config import settings


class ConfigStore(BaseModel):
    """Thread-safe singleton configuration store with TTL-based cache invalidation.
    Stores various configuration data of Cabbo like geography, cab types, fuel types, trip types, and pricing configurations loaded from the database for quick access.
    Uses Pydantic for data validation and serialization.
    """

    # Singleton instance
    _instance: ClassVar[Optional["ConfigStore"]] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    # Cache TTL in seconds (default: 1 day)
    CACHE_TTL_SECONDS: int = Field(
        default=86400, description="Time-to-live for cached configurations in seconds"
    )

    outstation: dict[str, MasterPricingConfiguration] = (
        {}
    )  # Includes state wise base and secondary pricing configs
    local: dict[str, MasterPricingConfiguration] = (
        {}
    )  # Includes region wise base and secondary pricing configs
    airport_pickup: dict[str, MasterPricingConfiguration] = (
        {}
    )  # Includes region wise base and secondary pricing configs
    airport_drop: dict[str, MasterPricingConfiguration] = (
        {}
    )  # Includes region wise base and secondary pricing configs

    geographies: Geographies = Field(
        default_factory=Geographies,
        description="In-memory store for geography configurations",
    )
    cabs: List[CabTypeSchema] = Field(
        default_factory=list,
        description="In-memory store for cab configurations",
    )
    fuel_types: List[FuelTypeSchema] = Field(
        default_factory=list,
        description="In-memory store for fuel type configurations",
    )
    trip_types: List[TripTypeSchema] = Field(
        default_factory=list,
        description="In-memory store for trip type configurations",
    )
    airport_locations: List[AirportSchema] = Field(
        default_factory=list,
        description="In-memory store for airport location configurations",
    )

    platform_fee: FixedPlatformFeeConfigurationSchema = Field(
        default_factory=FixedPlatformFeeConfigurationSchema,
        description="In-memory store for fixed platform fee configurations",
    )

    # ✅ Private attributes using PrivateAttr (not validated by Pydantic)
    _store: dict = PrivateAttr(default_factory=dict)
    _last_loaded_at: Optional[datetime] = PrivateAttr(default=None)
    _is_initialized: bool = PrivateAttr(default=False)
    _lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)

    class Config:
        arbitrary_types_allowed = True

    @classmethod
    def get_instance(cls) -> "ConfigStore":
        """Get or create the singleton instance."""
        print("ConfigStore.get_instance() called")

        if cls._instance is None:
            print("Instance is None, acquiring lock...")
            with cls._instance_lock:
                print("Lock acquired, checking again...")
                if cls._instance is None:
                    print("Creating new instance...")
                    cls._instance = super(ConfigStore, cls).__new__(cls)
                    print("Calling BaseModel.__init__...")
                    BaseModel.__init__(cls._instance)
                    print("Instance created successfully")

        print("Returning instance")
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset the singleton instance (useful for testing)."""
        with cls._instance_lock:
            if cls._instance is not None:
                cls._instance._is_initialized = False
                cls._instance._last_loaded_at = None
            cls._instance = None

    def initialize_config_store(self, db: Session):
        """Initial load of all configurations from database."""
        # Only initialize if not already initialized or cache expired
        if not self._is_initialized or not self.is_cache_valid():
            print("ConfigStore: Starting initialization...")
            self._lazy_load(db)
            print("ConfigStore initialization completed.")
        else:
            print(
                "ConfigStore already initialized with valid cache. Skipping initialization."
            ) 

    def is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        if not self.is_initialized() or self._last_loaded_at is None:
            return False

        elapsed = datetime.now(timezone.utc) - self._last_loaded_at
        return elapsed.total_seconds() < self.CACHE_TTL_SECONDS

    def is_initialized(self) -> bool:
        """Check if store has been initialized."""
        return self._is_initialized

    def _initialize_pricing_configuration(self):
        return MasterPricingConfiguration()

    def warm_up_cache(self, db: Session):
        """Force reload all configurations from database, bypassing cache."""
        with self._lock:
            self._clear_all_data()
            self._load_all_configurations(db)
            self._last_loaded_at = datetime.now(timezone.utc)
            self._is_initialized = True
            print("Configuration store force reloaded successfully.")

    def _lazy_load(self, db: Session):
        """
        Lazy load configurations on first request or when cache expires.
        Thread-safe and ensures only one load happens at a time.
        """
        # Fast path: cache is valid
        if self.is_cache_valid():
            print("Cache is valid, no need to reload.")
            if not self._is_initialized:
                self._is_initialized = True
            return

        # Slow path: need to reload
        with self._lock:
            # Double-check after acquiring lock (another thread may have loaded the force reload meanwhile)
            if self.is_cache_valid():
                print("Cache is valid after acquiring lock, no need to reload.")
                if not self._is_initialized:
                    self._is_initialized = True
                return

            print("ConfigStore: Loading all configurations from database...")
            try:
                self._load_all_configurations(db)
                self._last_loaded_at = datetime.now(timezone.utc)
                self._is_initialized = True
                print("Configuration store loaded/reloaded successfully.")
            except Exception as e:
                print(f"ERROR loading configurations: {e}")
                import traceback

                traceback.print_exc()
                self._is_initialized = False
                raise

    def _load_all_configurations(self, db: Session):
        """Load all configurations from database."""
        # Load in dependency order
        print("Step 1: Loading cabs...")
        self._retrieve_and_set_cabs(db)

        print("Step 2: Loading fuel types...")
        self._retrieve_and_set_fuel_types(db)

        print("Step 3: Loading trip types...")
        self._retrieve_and_set_trip_types(db)

        print("Step 4: Loading airport locations...")
        self._retrieve_and_set_airport_locations(db)

        print("Step 5: Loading geographies...")
        self._retrieve_and_set_serviceable_geographies(db)

        # Load pricing configurations
        print("Step 6: Loading outstation pricing...")
        self._retrieve_and_set_outstation_pricing(db)

        print("Step 7: Loading local pricing...")
        self._retrieve_and_set_local_pricing(db)

        print("Step 8: Loading airport pickup pricing...")
        self._retrieve_and_set_airport_pricing(TripTypeEnum.airport_pickup, db)

        print("Step 9: Loading airport drop pricing...")
        self._retrieve_and_set_airport_pricing(TripTypeEnum.airport_drop, db)

        # Load platform fee
        print("Step 10: Loading platform fee information...")
        self._retrieve_and_set_platform_fee_info(db)

         

    def _clear_all_data(self):
        """Clear all cached data."""
        self.outstation = {}
        self.local = {}
        self.airport_pickup = {}
        self.airport_drop = {}
        self.geographies = Geographies()
        self.cabs = []
        self.fuel_types = []
        self.trip_types = []
        self.platform_fee = FixedPlatformFeeConfigurationSchema()
        self._store.clear()
        self._is_initialized = False
        self._last_loaded_at = None

    def get_cache_metadata(self) -> dict:
        """Return cache metadata for monitoring/debugging."""
        return {
            "is_initialized": self._is_initialized,
            "last_loaded_at": (
                self._last_loaded_at.isoformat() if self._last_loaded_at else None
            ),
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "is_valid": self.is_cache_valid(),
            "time_until_expiry_seconds": (
                self.CACHE_TTL_SECONDS
                - (datetime.now(timezone.utc) - self._last_loaded_at).total_seconds()
                if self._last_loaded_at
                else None
            ),
        }

    # ===== SETTERS AND GETTERS =====
    def set(
        self,
        key,
        value: Union[
            dict[str, MasterPricingConfiguration],
            Geographies,
            List[CabTypeSchema],
            List[FuelTypeSchema],
            List[TripTypeSchema],
            FixedPlatformFeeConfigurationSchema,
        ],
    ):
        """Set a configuration value."""
        self._store[key] = value

    def get(self, key, default=None):
        """Get a configuration value."""
        return self._store.get(key, default)

    def delete(self, key):
        """Delete a configuration value."""
        if key in self._store:
            del self._store[key]

    def clear(self):
        """Clear all configuration values."""
        self._store.clear()

    def _set_outstation_pricing(
        self, outstation_data: dict[str, MasterPricingConfiguration]
    ):
        """Set outstation pricing data for a specific state."""
        self.set(TripTypeEnum.outstation.value, outstation_data)
        self.outstation = outstation_data

    def get_outstation_pricing(self) -> dict[str, MasterPricingConfiguration]:
        """Retrieve outstation pricing data."""
        # Attempt to initialize store if not already done
        return self.outstation

    def _set_local_pricing(self, local_data: dict[str, MasterPricingConfiguration]):
        """Set local pricing data for a specific region."""
        self.set(TripTypeEnum.local.value, local_data)
        self.local = local_data

    def get_local_pricing(self) -> dict[str, MasterPricingConfiguration]:
        """Retrieve local pricing data."""
        return self.local

    def _set_airport_pickup_pricing(
        self, airport_pickup_data: dict[str, MasterPricingConfiguration]
    ):
        """Set airport pickup pricing data for a specific region."""
        self.set(TripTypeEnum.airport_pickup.value, airport_pickup_data)
        self.airport_pickup = airport_pickup_data

    def get_airport_pickup_pricing(self) -> dict[str, MasterPricingConfiguration]:
        """Retrieve airport pickup pricing data."""
        return self.airport_pickup

    def _set_airport_drop_pricing(
        self, airport_drop_data: dict[str, MasterPricingConfiguration]
    ):
        """Set airport drop pricing data for a specific region."""
        self.set(TripTypeEnum.airport_drop.value, airport_drop_data)
        self.airport_drop = airport_drop_data

    def get_airport_drop_pricing(self) -> dict[str, MasterPricingConfiguration]:
        """Retrieve airport drop pricing data."""
        return self.airport_drop

    def _set_geography(self, geography_data: Geographies):
        """Load geography configurations into the store."""
        self.geographies = geography_data
        self.set("geographies", geography_data)

    def get_geography(self) -> Geographies:
        """Retrieve geography configurations from the store."""
        return self.geographies

    def _set_cabs(self, cab_data: List[CabTypeSchema]):
        """Load cab configurations into the store."""
        self.cabs = cab_data
        self.set("cabs", cab_data)

    def get_cabs(self) -> List[CabTypeSchema]:
        """Retrieve cab configurations from the store."""
        return self.cabs

    def _set_fuel_types(self, fuel_type_data: List[FuelTypeSchema]):
        """Load fuel type configurations into the store."""
        self.fuel_types = fuel_type_data
        self.set("fuel_types", fuel_type_data)

    def get_fuel_types(self) -> List[FuelTypeSchema]:
        """Retrieve fuel type configurations from the store."""
        return self.fuel_types

    def _set_trip_types(self, trip_type_data: List[TripTypeSchema]):
        """Load trip type configurations into the store."""
        self.trip_types = trip_type_data
        self.set("trip_types", trip_type_data)
    
    def _set_airport_locations(self, airport_location_data: List[AirportSchema]):
        """Load airport location configurations into the store."""
        self.airport_locations = airport_location_data
        self.set("airport_locations", airport_location_data)

    def get_trip_types(self) -> List[TripTypeSchema]:
        """Retrieve trip type configurations from the store."""
        return self.trip_types

    def _set_platform_fee(self, platform_fee_data: FixedPlatformFeeConfigurationSchema):
        """Load fixed platform fee configurations into the store."""
        self.platform_fee = platform_fee_data
        self.set("platform_fee", platform_fee_data)

    def get_platform_fee(self) -> FixedPlatformFeeConfigurationSchema:
        """Retrieve fixed platform fee configurations from the store."""
        return self.platform_fee

    # ===== DATA RETRIEVAL HELPERS =====
    def _retrieve_and_set_cabs(self, db: Session):
        """Load cab data into the store."""
        print("Loading cab data into ConfigStore...")
        self._set_cabs(get_all_cabs(db))

    def _retrieve_and_set_fuel_types(self, db: Session):
        """Load fuel type data into the store."""
        print("Loading fuel type data into ConfigStore...")
        self._set_fuel_types(get_all_fuel_types(db))

    def _retrieve_and_set_trip_types(self, db: Session):
        """Load trip type data into the store."""
        print("Loading trip type data into ConfigStore...")
        self._set_trip_types(get_all_trip_types(db))
    
    def _retrieve_and_set_airport_locations(self, db: Session):
        """Load airport location data into the store."""
        print("Loading airport location data into ConfigStore...")
        from services.airport_service import get_all_airports
        self._set_airport_locations(get_all_airports(db))

    def _retrieve_and_set_serviceable_geographies(self, db: Session):
        try:
            """Load country data from the database into the store."""
            print("Loading geography data into ConfigStore...")
            countries = get_all_countries(db)
            country_dict = {country.country_code: country for country in countries}
            self.geographies.countries = country_dict

            states = get_all_states(db)
            state_dict = {state.state_code: state for state in states}
            self.geographies.states = state_dict

            regions = get_all_regions(db)
            region_dict = {region.region_code: region for region in regions}
            self.geographies.regions = region_dict

            country_server = settings.COUNTRY_CODE.upper()
            if country_server in country_dict:
                self.geographies.country_server = country_dict[country_server]

            self._set_geography(self.geographies)
        except Exception as e:
            print(f"Error loading geography data: {e}")
            import traceback
            traceback.print_exc()
            raise

    def _retrieve_and_set_outstation_pricing(self, db: Session):
        """Load outstation master data from the database into the store."""
        print("Loading outstation pricing data into ConfigStore...")
        outstation_trip_type = self._retrieve_trip_type(
            trip_type=TripTypeEnum.outstation, db=db
        )

        if not outstation_trip_type:
            return
        base_pricings = get_base_pricings_outstation(db)
        # Load TripwisePricingConfiguration for outstation

        trip_configs = self._retrieve_trip_configs(id=outstation_trip_type.id, db=db)

        # Group by state_code
        outstation_data: dict[str, MasterPricingConfiguration] = {}

        # First, group base pricings by state_code
        for pricing, cab, fuel in base_pricings:
            # Model validate pricing, cab, fuel
            _pricing: OutstationCabPricingSchema = (
                OutstationCabPricingSchema.model_validate(pricing)
            )
            _cab: CabTypeSchema = CabTypeSchema.model_validate(cab)
            _fuel: FuelTypeSchema = FuelTypeSchema.model_validate(fuel)
            if _pricing.state_id:

                state = get_state_by_id(_pricing.state_id, db)

                if state:
                    state_code = state.state_code
                    if state_code not in outstation_data:
                        outstation_data[state_code] = (
                            self._initialize_pricing_configuration()
                        )
                    outstation_data[state_code].base_pricing.append(
                        (_pricing, _cab, _fuel)
                    )
        for trip_config in trip_configs:
            if trip_config.state_id:

                state = get_state_by_id(trip_config.state_id, db)
                if state:
                    state_code = state.state_code
                    if state_code not in outstation_data:
                        outstation_data[state_code] = (
                            self._initialize_pricing_configuration()
                        )

                    outstation_data[state_code].auxiliary_pricing.common = trip_config
                    # Find the night pricing configuration for the state and set it
                    night_pricing_schema = get_night_pricing_configuration(
                        db=db, id=state.id, by_state=True
                    )
                    if night_pricing_schema:
                        outstation_data[state_code].auxiliary_pricing.night = (
                            night_pricing_schema
                        )
                    # Get the permit fee configuration for the state and set it
                    permit_fee_schema = get_permit_fee_configuration(db, state.id)

                    if permit_fee_schema:
                        outstation_data[state_code].auxiliary_pricing.permit = (
                            permit_fee_schema
                        )
        # Load cancelation policy config in store for outstation trips for each state
        for state_code, pricing_config in outstation_data.items():
            cancellation_policy = get_cancellation_policy_by_state_code(state_code, db)
            if cancellation_policy:
                pricing_config.auxiliary_pricing.cancellation_policy = (
                    cancellation_policy
                )

        self._set_outstation_pricing(outstation_data)

    def _retrieve_and_set_local_pricing(self, db: Session):
        """Load local pricing data from the database into the store."""
        print("Loading local pricing data into ConfigStore...")
        local_trip_type = self._retrieve_trip_type(trip_type=TripTypeEnum.local, db=db)
        if not local_trip_type:
            return
        base_pricings = get_base_pricings_local(db)
        # Load TripwisePricingConfiguration for local

        trip_configs = self._retrieve_trip_configs(local_trip_type.id, db)
        # Group by region_code
        local_data: dict[str, MasterPricingConfiguration] = {}
        # First, group base pricings by region_code
        for pricing, cab, fuel in base_pricings:
            # Model validate pricing, cab, fuel

            _pricing = LocalCabPricingSchema.model_validate(pricing)
            _cab = CabTypeSchema.model_validate(cab)
            _fuel = FuelTypeSchema.model_validate(fuel)
            if _pricing.region_id:
                region = get_region_by_id(_pricing.region_id, db)

                if region:
                    region_code = region.region_code
                    if region_code not in local_data:
                        local_data[region_code] = (
                            self._initialize_pricing_configuration()
                        )

                    local_data[region_code].base_pricing.append((_pricing, _cab, _fuel))

        for trip_config in trip_configs:
            if trip_config.region_id:
                region = get_region_by_id(trip_config.region_id, db)
                if region:
                    region_code = region.region_code
                    if region_code not in local_data:
                        local_data[region_code] = (
                            self._initialize_pricing_configuration()
                        )

                    local_data[region_code].auxiliary_pricing.common = trip_config
                    # Get the night pricing configuration for the region and set it
                    night_pricing_schema = get_night_pricing_configuration(
                        db=db, id=region.id
                    )
                    if night_pricing_schema:
                        local_data[region_code].auxiliary_pricing.night = (
                            night_pricing_schema
                        )
        # Load cancelation policy config in store for local trips for each region
        for region_code, pricing_config in local_data.items():
            cancellation_policy = get_cancellation_policy_by_region_code(
                region_code, db
            )
            if cancellation_policy:
                pricing_config.auxiliary_pricing.cancellation_policy = (
                    cancellation_policy
                )
        # - Load trip package config per region inside local trip config data
        for region_code, pricing_config in local_data.items():
            trip_package_config_list = get_trip_package_configuration_list_by_region_code(
                region_code, db
            )
            if trip_package_config_list:
                pricing_config.auxiliary_pricing.trip_packages= trip_package_config_list

        self._set_local_pricing(local_data)

    def _retrieve_and_set_airport_pricing(self, trip_type: TripTypeEnum, db: Session):
        """Load all airport pricing data from the database into the store."""
        print("Loading airport pricing data into ConfigStore...")
        if trip_type not in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
            return
        airport_trip_type = self._retrieve_trip_type(trip_type=trip_type, db=db)
        if not airport_trip_type:
            return
        base_pricings = get_base_pricings_airport(db)
        # Load TripwisePricingConfiguration for airport
        trip_configs = self._retrieve_trip_configs(id=airport_trip_type.id, db=db)
        # Group by region_code
        airport_data: dict[str, MasterPricingConfiguration] = {}
        # First, group base pricings by region_code
        for pricing, cab, fuel in base_pricings:
            # Model validate pricing, cab, fuel
            _pricing = AirportCabPricingSchema.model_validate(pricing)
            _cab = CabTypeSchema.model_validate(cab)
            _fuel = FuelTypeSchema.model_validate(fuel)

            if _pricing.region_id:
                region = get_region_by_id(_pricing.region_id, db)
                if region:
                    region_code = region.region_code
                    if region_code not in airport_data:
                        airport_data[region_code] = (
                            self._initialize_pricing_configuration()
                        )

                    airport_data[region_code].base_pricing.append(
                        (_pricing, _cab, _fuel)
                    )
        for trip_config in trip_configs:
            if trip_config.region_id:
                region = get_region_by_id(trip_config.region_id, db)
                if region:
                    region_code = region.region_code
                    if region_code not in airport_data:
                        airport_data[region_code] = (
                            self._initialize_pricing_configuration()
                        )

                    airport_data[region_code].auxiliary_pricing.common = trip_config
                    # No night pricing for airport trips
                    # No permit fee for airport trips
        # Load cancelation policy config in store for local trips for each region
        for region_code, pricing_config in airport_data.items():
            cancellation_policy = get_cancellation_policy_by_region_code(
                region_code, db
            )
            if cancellation_policy:
                pricing_config.auxiliary_pricing.cancellation_policy = (
                    cancellation_policy
                )

        if trip_type == TripTypeEnum.airport_pickup:
            self._set_airport_pickup_pricing(airport_data)
        elif trip_type == TripTypeEnum.airport_drop:
            self._set_airport_drop_pricing(airport_data)

    def _retrieve_and_set_platform_fee_info(self, db: Session):
        """Load fixed platform fee data from the database into the store."""
        print("Loading platform fee data into ConfigStore...")

        platform_fee = get_fixed_platform_pricing_configuration(db=db)
        if not platform_fee:
            return
        self._set_platform_fee(platform_fee)

    def _retrieve_trip_configs(
        self, id: str, db: Session
    ) -> List[CommonPricingConfigurationSchema]:
        print("Loading common pricing configurations into ConfigStore...")
        return get_common_pricing_configurations_by_trip_type_id(trip_type_id=id, db=db)

    def _retrieve_trip_type(
        self, trip_type: TripTypeEnum, db: Session
    ) -> TripTypeSchema:
        print("Loading trip type data into ConfigStore...")
        return get_trip_type_id_by_trip_type(
            trip_type=trip_type, db=db, include_id_only=False
        )

    