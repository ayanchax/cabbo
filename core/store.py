from typing import List, Union
from fastapi import Depends
from pydantic import BaseModel, Field
from models.cab.cab_orm import CabType, FuelType
from models.geography.country_schema import CountrySchema
from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema
from models.pricing.pricing_orm import (
    AirportCabPricing,
    FixedPlatformPricing,
    LocalCabPricing,
    OutstationCabPricing,
    TripwisePricingConfiguration,
)
from db.database import get_mysql_session
from sqlalchemy.orm import Session

from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import TripTypeMaster
from services.geography_service import (
    get_all_countries,
    get_all_regions,
    get_all_states,
    get_all_states,
    get_region_by_id,
    get_state_by_id,
)


class TripMasterConfiguration(BaseModel):
    base_pricing: List[
        tuple[
            Union[OutstationCabPricing, AirportCabPricing, LocalCabPricing],
            CabType,
            FuelType,
        ]
    ] = []
    config: TripwisePricingConfiguration = None
    
    night: dict = (
        {}
    )  # Includes region wise and state wise night pricing configurations for outstation and local
    permit: dict = (
        {}
    )  # Includes permit fee configurations state wise for outstation trips
    

class Geographies(BaseModel):
    regions: dict[str, RegionSchema] = {}  # region_code -> RegionSchema
    states: dict[str, StateSchema] = {}  # state_code -> StateSchema
    countries: dict[str, CountrySchema] = {}  # country_code -> CountrySchema


class ConfigStore(BaseModel):

    outstation: dict[str, TripMasterConfiguration] = (
        {}
    )  # Includes state wise base and secondary pricing configs
    local: dict[str, TripMasterConfiguration] = (
        {}
    )  # Includes region wise base and secondary pricing configs
    airport_pickup: dict[str, TripMasterConfiguration] = (
        {}
    )  # Includes region wise base and secondary pricing configs
    airport_drop: dict[str, TripMasterConfiguration] = (
        {}
    )  # Includes region wise base and secondary pricing configs

    geographies: Geographies = Field(
        default_factory=Geographies,
        description="In-memory store for geography configurations",
    )
    cabs: List[CabType] = Field(
        default_factory=list,
        description="In-memory store for cab configurations",
    )
    fuel_types: List[FuelType] = Field(
        default_factory=list,
        description="In-memory store for fuel type configurations",
    )
    trip_types: List[TripTypeMaster] = Field(
        default_factory=list,
        description="In-memory store for trip type configurations",
    )

    platform_fee: FixedPlatformPricing = Field(
        default_factory=FixedPlatformPricing,
        description="In-memory store for fixed platform fee configurations",
    )

    def __init__(self):
        self._store = {}

    def set(
        self,
        key,
        value: Union[
            dict[str, TripMasterConfiguration],
            Geographies,
            List[CabType],
            List[FuelType],
            List[TripTypeMaster],
            FixedPlatformPricing,
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

    def _set_outstation_data(
        self, outstation_data: dict[str, TripMasterConfiguration]
    ):
        """Set outstation pricing data for a specific state."""
        self.set(TripTypeEnum.outstation.value, outstation_data)
        self.outstation = outstation_data

    def get_outstation_data(self) -> dict[str, TripMasterConfiguration]:
        """Retrieve outstation pricing data."""
        return self.get(TripTypeEnum.outstation.value, self.outstation)

    def _set_local_data(self, local_data: dict[str, TripMasterConfiguration]):
        """Set local pricing data for a specific region."""
        self.set(TripTypeEnum.local.value, local_data)
        self.local = local_data

    def get_local_data(self) -> dict[str, TripMasterConfiguration]:
        """Retrieve local pricing data."""
        return self.get(TripTypeEnum.local.value, self.local)

    def _set_airport_pickup_data(
        self, airport_pickup_data: dict[str, TripMasterConfiguration]
    ):
        """Set airport pickup pricing data for a specific region."""
        self.set(TripTypeEnum.airport_pickup.value, airport_pickup_data)
        self.airport_pickup = airport_pickup_data

    def get_airport_pickup_data(self) -> dict[str, TripMasterConfiguration]:
        """Retrieve airport pickup pricing data."""
        return self.get(TripTypeEnum.airport_pickup.value, self.airport_pickup)

    def _set_airport_drop_data(
        self, airport_drop_data: dict[str, TripMasterConfiguration]
    ):
        """Set airport drop pricing data for a specific region."""
        self.set(TripTypeEnum.airport_drop.value, airport_drop_data)
        self.airport_drop = airport_drop_data

    def get_airport_drop_data(self) -> dict[str, TripMasterConfiguration]:
        """Retrieve airport drop pricing data."""
        return self.get(TripTypeEnum.airport_drop.value, self.airport_drop)

    def _set_geography_config(self, geography_data: Geographies):
        """Load geography configurations into the store."""
        self.geographies = geography_data
        self.set("geographies", geography_data)

    def get_geography_config(self) -> Geographies:
        """Retrieve geography configurations from the store."""
        return self.get("geographies", self.geographies)

    def _set_cab_config(self, cab_data: List[CabType]):
        """Load cab configurations into the store."""
        self.cabs = cab_data
        self.set("cabs", cab_data)

    def get_cab_config(self) -> List[CabType]:
        """Retrieve cab configurations from the store."""
        return self.get("cabs", self.cabs)

    def _set_fuel_type_config(self, fuel_type_data: List[FuelType]):
        """Load fuel type configurations into the store."""
        self.fuel_types = fuel_type_data
        self.set("fuel_types", fuel_type_data)

    def get_fuel_type_config(self) -> List[FuelType]:
        """Retrieve fuel type configurations from the store."""
        return self.get("fuel_types", self.fuel_types)

    def _set_trip_type_config(self, trip_type_data: List[TripTypeMaster]):
        """Load trip type configurations into the store."""
        self.trip_types = trip_type_data
        self.set("trip_types", trip_type_data)

    def get_trip_type_config(self) -> List[TripTypeMaster]:
        """Retrieve trip type configurations from the store."""
        return self.get("trip_types", self.trip_types)
    
    def _set_platform_fee_config(self, platform_fee_data: FixedPlatformPricing):
        """Load fixed platform fee configurations into the store."""
        self.platform_fee = platform_fee_data
        self.set("platform_fee", platform_fee_data)
    
    def get_platform_fee_config(self) -> FixedPlatformPricing:
        """Retrieve fixed platform fee configurations from the store."""
        return self.get("platform_fee", self.platform_fee)

    def _load_cabs(self, db: Session = Depends(get_mysql_session)):
        """Load cab data into the store."""
        cabs = db.query(CabType).all()
        self.cabs = cabs
        self._set_cab_config(cabs)

    def _load_fuel_types(self, db: Session = Depends(get_mysql_session)):
        """Load fuel type data into the store."""
        fuel_types = db.query(FuelType).all()
        self.fuel_types = fuel_types
        self._set_fuel_type_config(fuel_types)

    def _load_trip_types(self, db: Session = Depends(get_mysql_session)):
        """Load trip type data into the store."""
        trip_types = db.query(TripTypeMaster).all()
        self.trip_types = trip_types
        self._set_trip_type_config(trip_types)

    def _load_geographies(self, db: Session = Depends(get_mysql_session)):
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

    def _load_outstation_master_data(self, db: Session = Depends(get_mysql_session)):
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

        trip_config = self._retrieve_trip_config(id=outstation_trip_type.id, db=db)

        # Group by state_code
        outstation_data = {}

        # First, group base pricings by state_code
        for pricing, cab, fuel in base_pricings:
            _pricing: OutstationCabPricing = pricing
            if _pricing.state_id:

                state = get_state_by_id(_pricing.state_id, db)

                if state:
                    state_code = state.state_code
                    if state_code not in outstation_data:
                        outstation_data[state_code] = self._initialize_trip_data()

                    outstation_data[state_code]["base_pricing"].append(
                        (_pricing, cab, fuel)
                    )

        if trip_config.state_id:

            state = get_state_by_id(trip_config.state_id, db)
            if state:
                state_code = state.state_code
                if state_code not in outstation_data:
                    outstation_data[state_code] = self._initialize_trip_data()
                outstation_data[state_code]["config"] = trip_config

        self._set_outstation_pricing(outstation_data)

    def _load_local_master_data(self, db: Session = Depends(get_mysql_session)):
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

        trip_config = self._retrieve_trip_config(local_trip_type.id, db)
        # Group by region_code
        local_data = {}
        # First, group base pricings by region_code
        for pricing, cab, fuel in base_pricings:
            _pricing: LocalCabPricing = pricing
            if _pricing.region_id:
                region = get_region_by_id(_pricing.region_id, db)

                if region:
                    region_code = region.region_code
                    if region_code not in local_data:
                        local_data[region_code] = self._initialize_trip_data()

                    local_data[region_code]["base_pricing"].append(
                        (_pricing, cab, fuel)
                    )

        if trip_config.region_id:
            region = get_region_by_id(trip_config.region_id, db)
            if region:
                region_code = region.region_code
                if region_code not in local_data:
                    local_data[region_code] = self._initialize_trip_data()
                local_data[region_code]["config"] = trip_config
        self._set_local_pricing(local_data)

    def _load_airport_pickup_data(self, db: Session = Depends(get_mysql_session)):
        """Load airport pickup pricing data from the database into the store."""
        self.load_airport_pricing_data(trip_type=TripTypeEnum.airport_pickup, db=db)

    def _load_airport_drop_data(self, db: Session = Depends(get_mysql_session)):
        """Load airport drop pricing data from the database into the store."""
        self._load_airport_master_data(trip_type=TripTypeEnum.airport_drop, db=db)

    def _load_airport_master_data(
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
        trip_config = self._retrieve_trip_config(id=airport_trip_type.id, db=db)
        # Group by region_code
        airport_data = {}
        # First, group base pricings by region_code
        for pricing, cab, fuel in base_pricings:
            _pricing: AirportCabPricing = pricing
            if _pricing.region_id:
                region = get_region_by_id(_pricing.region_id, db)
                if region:
                    region_code = region.region_code
                    if region_code not in airport_data:
                        airport_data[region_code] = self._initialize_trip_data()

                    airport_data[region_code]["base_pricing"].append(
                        (_pricing, cab, fuel)
                    )
        if trip_config.region_id:
            region = get_region_by_id(trip_config.region_id, db)
            if region:
                region_code = region.region_code
                if region_code not in airport_data:
                    airport_data[region_code] = self._initialize_trip_data()
                airport_data[region_code]["config"] = trip_config
        if trip_type == TripTypeEnum.airport_pickup:
            self._set_airport_pickup_pricing(airport_data)
        elif trip_type == TripTypeEnum.airport_drop:
            self._set_airport_drop_pricing(airport_data)

    def _load_platform_fee_data(self, db: Session = Depends(get_mysql_session)):
        """Load fixed platform fee data from the database into the store."""
        platform_fee_data = db.query(FixedPlatformPricing).first()
        if not platform_fee_data:
            return
        self._set_platform_fee_config(platform_fee_data)

    def _retrieve_trip_config(
        self, id: str, db: Session = Depends(get_mysql_session)
    ) -> TripwisePricingConfiguration:
        return (
            db.query(TripwisePricingConfiguration)
            .filter(TripwisePricingConfiguration.trip_type_id == id)
            .first()
        )

    def _retrieve_trip_type(
        self, trip_type: TripTypeEnum, db: Session = Depends(get_mysql_session)
    ) -> TripTypeMaster:
        return (
            db.query(TripTypeMaster)
            .filter(TripTypeMaster.trip_type == trip_type)
            .first()
        )

    def _initialize_trip_data(self):
        return {
            "base_pricing": [],
            "config": None,
        }
