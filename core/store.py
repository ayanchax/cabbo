from datetime import datetime, timezone
import threading
from typing import List, Optional, Union
from fastapi import Depends
from pydantic import BaseModel, Field
from models.cab.cab_orm import CabType, FuelType
from models.cab.cab_schema import CabTypeSchema, FuelTypeSchema
from models.geography.geography_schema import Geographies
from models.pricing.pricing_orm import (
    AirportCabPricing,
    FixedPlatformPricingConfiguration,
    LocalCabPricing,
    NightPricingConfiguration,
    OutstationCabPricing,
    CommonPricingConfiguration,
    PermitFeeConfiguration,
)
from db.database import get_mysql_session
from sqlalchemy.orm import Session

from models.pricing.pricing_schema import (
    AirportCabPricingSchema,
    CommonPricingConfigurationSchema,
    FixedPlatformFeeConfigurationSchema,
    LocalCabPricingSchema,
    MasterPricingConfiguration,
    NightPricingConfigurationSchema,
    OutstationCabPricingSchema,
    PermitFeeConfigurationSchema,
)
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import TripTypeMaster
from models.trip.trip_schema import TripTypeSchema
from services.geography_service import (
    get_all_countries,
    get_all_regions,
    get_all_states,
    get_all_states,
    get_region_by_id,
    get_state_by_id,
)
from services.pricing_service import get_common_pricing_configurations_by_trip_type_id
from services.trip_service import get_all_trip_types, get_trip_type_id_by_trip_type


class ConfigStore(BaseModel):
    """Thread-safe configuration store with TTL-based cache invalidation."""
    
    # Cache TTL in seconds (default: 1 hour)
    CACHE_TTL_SECONDS: int = Field(default=3600, description="Time-to-live for cached configurations in seconds")
    
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

    platform_fee: FixedPlatformFeeConfigurationSchema = Field(
        default_factory=FixedPlatformFeeConfigurationSchema,
        description="In-memory store for fixed platform fee configurations",
    )

    # Cache metadata
    _last_loaded_at: Optional[datetime] = None
    _is_initialized: bool = False
    _lock: threading.Lock = Field(default_factory=threading.Lock, exclude=True)

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, **data):
        super().__init__(**data)
        self._store = {}
        self._lock = threading.Lock()
        self._last_loaded_at = None
        self._is_initialized = False
    
    def initialize_config_store(self, db: Session = Depends(get_mysql_session)):
        """Initial load of all configurations from database."""
        self._lazy_load(db)
            
    
    def is_cache_valid(self) -> bool:
        """Check if cache is still valid based on TTL."""
        if not self.is_initialized() or self._last_loaded_at is None:
            return False
        
        elapsed = datetime.now(timezone.utc) - self._last_loaded_at
        return elapsed.total_seconds() < self.CACHE_TTL_SECONDS

    def is_initialized(self) -> bool:
        """Check if store has been initialized."""
        return self._is_initialized

    def force_reload_config_store(self, db: Session = Depends(get_mysql_session)):
        """Force reload all configurations from database, bypassing cache."""
        with self._lock:
            self._clear_all_data()
            self._load_all_configurations(db)
            self._last_loaded_at = datetime.now(timezone.utc)
            self._is_initialized = True
            print("Configuration store force reloaded successfully.")
    
    def _lazy_load(self, db: Session = Depends(get_mysql_session)):
        """
        Lazy load configurations on first request or when cache expires.
        Thread-safe and ensures only one load happens at a time.
        """
        # Fast path: cache is valid
        if self.is_cache_valid():
            print("Cache is valid, no need to reload.")
            return
        
        # Slow path: need to reload
        with self._lock:
            # Double-check after acquiring lock (another thread may have loaded the force reload meanwhile)
            if self.is_cache_valid():
                print("Cache is valid after acquiring lock, no need to reload.")
                return
            
            self._load_all_configurations(db)
            self._last_loaded_at = datetime.now(timezone.utc)
            self._is_initialized = True
            print("Configuration store loaded/reloaded successfully.")

    def _load_all_configurations(self, db: Session):
        """Load all configurations from database."""
        # Load in dependency order
        self._retrieve_and_set_cabs(db)
        self._retrieve_and_set_fuel_types(db)
        self._retrieve_and_set_trip_types(db)
        self._retrieve_and_set_serviceable_geographies(db)
        
        # Load pricing configurations
        self._retrieve_and_set_outstation_pricing(db)
        self._retrieve_and_set_local_pricing(db)
        self._retrieve_and_set_airport_pricing(TripTypeEnum.airport_pickup, db)
        self._retrieve_and_set_airport_pricing(TripTypeEnum.airport_drop, db)
        
        # Load platform fee
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
            "last_loaded_at": self._last_loaded_at.isoformat() if self._last_loaded_at else None,
            "cache_ttl_seconds": self.CACHE_TTL_SECONDS,
            "is_valid": self.is_cache_valid(),
            "time_until_expiry_seconds": (
                self.CACHE_TTL_SECONDS - (datetime.now(timezone.utc) - self._last_loaded_at).total_seconds()
                if self._last_loaded_at
                else None
            ),
        }

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
        val=  self.get(TripTypeEnum.outstation.value, None)
        if val is None:
            self._retrieve_and_set_outstation_pricing()
        return val or self.outstation

    def _set_local_pricing(self, local_data: dict[str, MasterPricingConfiguration]):
        """Set local pricing data for a specific region."""
        self.set(TripTypeEnum.local.value, local_data)
        self.local = local_data

    def get_local_pricing(self) -> dict[str, MasterPricingConfiguration]:
        """Retrieve local pricing data."""
        val=  self.get(TripTypeEnum.local.value, None)
        if val is None:
            self._retrieve_and_set_local_pricing()
        return val or self.local

    def _set_airport_pickup_pricing(
        self, airport_pickup_data: dict[str, MasterPricingConfiguration]
    ):
        """Set airport pickup pricing data for a specific region."""
        self.set(TripTypeEnum.airport_pickup.value, airport_pickup_data)
        self.airport_pickup = airport_pickup_data

    def get_airport_pickup_pricing(self) -> dict[str, MasterPricingConfiguration]:
        """Retrieve airport pickup pricing data."""
        val=  self.get(TripTypeEnum.airport_pickup.value, None)
        if val is None:
            self._retrieve_and_set_airport_pricing(trip_type=TripTypeEnum.airport_pickup)
        return val or self.airport_pickup

    def _set_airport_drop_pricing(
        self, airport_drop_data: dict[str, MasterPricingConfiguration]
    ):
        """Set airport drop pricing data for a specific region."""
        self.set(TripTypeEnum.airport_drop.value, airport_drop_data)
        self.airport_drop = airport_drop_data

    def get_airport_drop_pricing(self) -> dict[str, MasterPricingConfiguration]:
        """Retrieve airport drop pricing data."""
        val=  self.get(TripTypeEnum.airport_drop.value, None)
        if val is None:
            self._retrieve_and_set_airport_pricing(trip_type=TripTypeEnum.airport_drop)
        return val or self.airport_drop

    def _set_geography(self, geography_data: Geographies):
        """Load geography configurations into the store."""
        self.geographies = geography_data
        self.set("geographies", geography_data)

    def get_geography(self) -> Geographies:
        """Retrieve geography configurations from the store."""
        val=  self.get("geographies", None)
        if val is None:
            self._retrieve_and_set_serviceable_geographies()
        return val or self.geographies

    def _set_cabs(self, cab_data: List[CabTypeSchema]):
        """Load cab configurations into the store."""
        self.cabs = cab_data
        self.set("cabs", cab_data)

    def get_cabs(self) -> List[CabTypeSchema]:
        """Retrieve cab configurations from the store."""
        val=  self.get("cabs", None)
        if val is None:
            self._retrieve_and_set_cabs()
        return val or self.cabs

    def _set_fuel_types(self, fuel_type_data: List[FuelTypeSchema]):
        """Load fuel type configurations into the store."""
        self.fuel_types = fuel_type_data
        self.set("fuel_types", fuel_type_data)

    def get_fuel_types(self) -> List[FuelTypeSchema]:
        """Retrieve fuel type configurations from the store."""
        val=  self.get("fuel_types", None)
        if val is None:
            self._retrieve_and_set_fuel_types()
        return val or self.fuel_types

    def _set_trip_types(self, trip_type_data: List[TripTypeSchema]):
        """Load trip type configurations into the store."""
        self.trip_types = trip_type_data
        self.set("trip_types", trip_type_data)

    def get_trip_types(self) -> List[TripTypeSchema]:
        """Retrieve trip type configurations from the store."""
        val=  self.get("trip_types", None)
        if val is None:
            self._retrieve_and_set_trip_types()
        return val or self.trip_types
    
    def _set_platform_fee(self, platform_fee_data: FixedPlatformFeeConfigurationSchema):
        """Load fixed platform fee configurations into the store."""
        self.platform_fee = platform_fee_data
        self.set("platform_fee", platform_fee_data)

    def get_platform_fee(self) -> FixedPlatformFeeConfigurationSchema:
        """Retrieve fixed platform fee configurations from the store."""
        val=  self.get("platform_fee", None)
        if val is None:
            self._retrieve_and_set_platform_fee_info()
        return val or self.platform_fee

    def _retrieve_and_set_cabs(self, db: Session = Depends(get_mysql_session)):
        """Load cab data into the store."""
        cabs = db.query(CabType).all()
        cab_schemas = [CabTypeSchema.model_validate(cab) for cab in cabs]
        self._set_cabs(cab_schemas)

    def _retrieve_and_set_fuel_types(self, db: Session = Depends(get_mysql_session)):
        """Load fuel type data into the store."""
        fuel_types = db.query(FuelType).all()
        fuel_type_schemas = [FuelTypeSchema.model_validate(fuel) for fuel in fuel_types]
        self._set_fuel_types(fuel_type_schemas)

    def _retrieve_and_set_trip_types(self, db: Session = Depends(get_mysql_session)):
        """Load trip type data into the store."""
        trip_types = get_all_trip_types(db)
        trip_type_schemas = [
            TripTypeSchema.model_validate(trip_type) for trip_type in trip_types
        ]
        self._set_trip_types(trip_type_schemas)

    def _retrieve_and_set_serviceable_geographies(
        self, db: Session = Depends(get_mysql_session)
    ):
        """Load country data from the database into the store."""
        countries = get_all_countries(db)
        country_dict = {country.code: country for country in countries}
        self.geographies.countries = country_dict

        states = get_all_states(db)
        state_dict = {state.code: state for state in states}
        self.geographies.states = state_dict

        regions = get_all_regions(db)
        region_dict = {region.code: region for region in regions}
        self.geographies.regions = region_dict

        self._set_geography_config(self.geographies)

    def _retrieve_and_set_outstation_pricing(
        self, db: Session = Depends(get_mysql_session)
    ):
        """Load outstation master data from the database into the store."""
        outstation_trip_type = self._retrieve_trip_type(
            trip_type=TripTypeEnum.outstation, db=db
        )

        if not outstation_trip_type:
            return
        base_pricings = (
            db.query(OutstationCabPricing, CabType, FuelType)
            .join(CabType, OutstationCabPricing.cab_type_id == CabType.id)
            .join(FuelType, OutstationCabPricing.fuel_type_id == FuelType.id)
            .filter(
                OutstationCabPricing.is_available_in_network == True,
            )  # Ensure only available cabs are considered
            .all()
        )
        # Load TripwisePricingConfiguration for outstation

        trip_configs = self._retrieve_trip_configs(id=outstation_trip_type.id, db=db)

        # Group by state_code
        outstation_data: dict[str, MasterPricingConfiguration] = {}

        # First, group base pricings by state_code
        for pricing, cab, fuel in base_pricings:
            _pricing: OutstationCabPricing = pricing
            _cab: CabType = cab
            _fuel: FuelType = fuel
            if _pricing.state_id:

                state = get_state_by_id(_pricing.state_id, db)

                if state:
                    state_code = state.state_code
                    if state_code not in outstation_data:
                        outstation_data[state_code] = (
                            self._initialize_pricing_configuration()
                        )

                    # Model validate pricing, cab, fuel
                    _pricing = OutstationCabPricingSchema.model_validate(_pricing)
                    _cab = CabTypeSchema.model_validate(_cab)
                    _fuel = FuelTypeSchema.model_validate(_fuel)
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
                    trip_config_schema = (
                        CommonPricingConfigurationSchema.model_validate(trip_config)
                    )
                    outstation_data[state_code].auxiliary_pricing.common = (
                        trip_config_schema
                    )
                    # Find the night pricing configuration for the state and set it
                    night_pricing = (
                        db.query(NightPricingConfiguration)
                        .filter(
                            NightPricingConfiguration.state_id == state.id,
                        )
                        .first()
                    )
                    if night_pricing:
                        night_pricing_schema = (
                            NightPricingConfigurationSchema.model_validate(
                                night_pricing
                            )
                        )
                        outstation_data[state_code].auxiliary_pricing.night = (
                            night_pricing_schema
                        )
                    # Get the permit fee configuration for the state and set it
                    permit_fee = (
                        db.query(PermitFeeConfiguration)
                        .filter(
                            PermitFeeConfiguration.state_id == state.id,
                        )
                        .first()
                    )
                    if permit_fee:
                        permit_fee_schema = PermitFeeConfigurationSchema.model_validate(
                            permit_fee
                        )
                        outstation_data[state_code].auxiliary_pricing.permit = (
                            permit_fee_schema
                        )

        self._set_outstation_pricing(outstation_data)

    def _retrieve_and_set_local_pricing(self, db: Session = Depends(get_mysql_session)):
        """Load local pricing data from the database into the store."""
        local_trip_type = self._retrieve_trip_type(trip_type=TripTypeEnum.local, db=db)
        if not local_trip_type:
            return
        base_pricings = (
            db.query(LocalCabPricing, CabType, FuelType)
            .join(CabType, LocalCabPricing.cab_type_id == CabType.id)
            .join(FuelType, LocalCabPricing.fuel_type_id == FuelType.id)
            .filter(
                LocalCabPricing.is_available_in_network == True,
            )  # Ensure only available cabs are considered
            .all()
        )
        # Load TripwisePricingConfiguration for local

        trip_configs = self._retrieve_trip_configs(local_trip_type.id, db)
        # Group by region_code
        local_data: dict[str, MasterPricingConfiguration] = {}
        # First, group base pricings by region_code
        for pricing, cab, fuel in base_pricings:
            _pricing: LocalCabPricing = pricing
            _cab: CabType = cab
            _fuel: FuelType = fuel
            if _pricing.region_id:
                region = get_region_by_id(_pricing.region_id, db)

                if region:
                    region_code = region.region_code
                    if region_code not in local_data:
                        local_data[region_code] = (
                            self._initialize_pricing_configuration()
                        )
                    # Model validate pricing, cab, fuel
                    _pricing = LocalCabPricingSchema.model_validate(_pricing)
                    _cab = CabTypeSchema.model_validate(_cab)
                    _fuel = FuelTypeSchema.model_validate(_fuel)
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
                trip_config_schema = CommonPricingConfigurationSchema.model_validate(
                    trip_config
                )
                local_data[region_code].auxiliary_pricing.common = trip_config_schema
                # Get the night pricing configuration for the region and set it
                night_pricing = (
                    db.query(NightPricingConfiguration)
                    .filter(NightPricingConfiguration.region_id == region.id)
                    .first()
                )
                if night_pricing:
                    night_pricing_schema = (
                        NightPricingConfigurationSchema.model_validate(night_pricing)
                    )
                    local_data[region_code].auxiliary_pricing.night = (
                        night_pricing_schema
                    )
        self._set_local_pricing(local_data)

    def _retrieve_and_set_airport_pricing(
        self, trip_type: TripTypeEnum, db: Session = Depends(get_mysql_session)
    ):
        """Load all airport pricing data from the database into the store."""
        if trip_type not in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
            return
        airport_trip_type = self._retrieve_trip_type(trip_type=trip_type, db=db)
        if not airport_trip_type:
            return
        base_pricings = (
            db.query(AirportCabPricing, CabType, FuelType)
            .join(CabType, AirportCabPricing.cab_type_id == CabType.id)
            .join(FuelType, AirportCabPricing.fuel_type_id == FuelType.id)
            .filter(
                AirportCabPricing.is_available_in_network == True
            )  # Ensure only available cabs are considered
            .all()
        )
        # Load TripwisePricingConfiguration for airport
        trip_configs = self._retrieve_trip_configs(id=airport_trip_type.id, db=db)
        # Group by region_code
        airport_data: dict[str, MasterPricingConfiguration] = {}
        # First, group base pricings by region_code
        for pricing, cab, fuel in base_pricings:
            _pricing: AirportCabPricing = pricing
            _cab: CabType = cab
            _fuel: FuelType = fuel
            if _pricing.region_id:
                region = get_region_by_id(_pricing.region_id, db)
                if region:
                    region_code = region.region_code
                    if region_code not in airport_data:
                        airport_data[region_code] = (
                            self._initialize_pricing_configuration()
                        )
                    # Model validate pricing, cab, fuel
                    _pricing = AirportCabPricingSchema.model_validate(_pricing)
                    _cab = CabTypeSchema.model_validate(_cab)
                    _fuel = FuelTypeSchema.model_validate(_fuel)

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
                    trip_config_schema = (
                        CommonPricingConfigurationSchema.model_validate(trip_config)
                    )

                    airport_data[region_code].auxiliary_pricing.common = (
                        trip_config_schema
                    )
                    # No night pricing for airport trips
                    # No permit fee for airport trips
        if trip_type == TripTypeEnum.airport_pickup:
            self._set_airport_pickup_pricing(airport_data)
        elif trip_type == TripTypeEnum.airport_drop:
            self._set_airport_drop_pricing(airport_data)

    def _retrieve_and_set_platform_fee_info(self, db: Session = Depends(get_mysql_session)):
        """Load fixed platform fee data from the database into the store."""
        platform_fee_data = db.query(FixedPlatformPricingConfiguration).first()
        if not platform_fee_data:
            return
        platform_fee_data_schema = FixedPlatformFeeConfigurationSchema.model_validate(
            platform_fee_data
        )
        self._set_platform_fee(platform_fee_data_schema)

    def _retrieve_trip_configs(
        self, id: str, db: Session = Depends(get_mysql_session)
    ) -> List[CommonPricingConfiguration]:
        return get_common_pricing_configurations_by_trip_type_id(trip_type_id=id, db=db)

    def _retrieve_trip_type(
        self, trip_type: TripTypeEnum, db: Session = Depends(get_mysql_session)
    ) -> TripTypeMaster:
        return get_trip_type_id_by_trip_type(
            trip_type=trip_type, db=db, include_id_only=False
        )

    def _initialize_pricing_configuration(self):
        return MasterPricingConfiguration()
