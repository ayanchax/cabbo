from fastapi import Depends
from pydantic import BaseModel, Field
from models.cab.cab_orm import CabType, FuelType
from models.pricing.pricing_orm import OutstationCabPricing
from db.database import get_mysql_session
from sqlalchemy.orm import Session


class Pricing(BaseModel):
    outstation: dict = {}  # Includes state wise base and secondary pricing configs
    local: dict = {}  # Includes region wise base and secondary pricing configs
    airport: dict = {}  # Includes region wise base and secondary pricing configs
    platform: dict = {}  # Includes fixed platform fee configs
    night: dict = {}  # Includes region wise and state wise night pricing configurations
    permit: dict = {}  # Includes permit fee configurations state wise


class Geographies(BaseModel):
    regions: dict = {}  # region_code -> RegionSchema
    states: dict = {}  # state_code -> StateSchema
    countries: dict = {}  # country_code -> CountrySchema


class ServiceableAreas(BaseModel):
    areas: dict = {}  # trip_type -> [region_code or state_code]


class ConfigStore(BaseModel):

    pricing: Pricing = Field(
        default_factory=Pricing,
        description="In-memory store for pricing configurations",
    )
    geographies: Geographies = Field(
        default_factory=Geographies,
        description="In-memory store for geography configurations",
    )

    serviceable_areas: ServiceableAreas = Field(
        default_factory=ServiceableAreas,
        description="In-memory store for serviceable area configurations",
    )

    cabs: list = Field(
        default_factory=list,
        description="In-memory store for cab configurations",
    )
    fuel_types: list = Field(
        default_factory=list,
        description="In-memory store for fuel type configurations",
    )
    trip_types: list = Field(
        default_factory=list,
        description="In-memory store for trip type configurations",
    )

    def __init__(self):
        self._store = {}

    def set(self, key, value):
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

    def set_pricing_config(self, pricing_data: Pricing):
        """Load pricing configurations into the store."""
        self.pricing = pricing_data
        self.set("pricing", pricing_data)

    def get_pricing_config(self) -> Pricing:
        """Retrieve pricing configurations from the store."""
        return self.get("pricing", self.pricing)

    def set_geography_config(self, geography_data: Geographies):
        """Load geography configurations into the store."""
        self.geographies = geography_data
        self.set("geographies", geography_data)

    def get_geography_config(self) -> Geographies:
        """Retrieve geography configurations from the store."""
        return self.get("geographies", self.geographies)

    def set_serviceable_area_config(self, serviceable_area_data: ServiceableAreas):
        """Load serviceable area configurations into the store."""
        self.serviceable_areas = serviceable_area_data
        self.set("serviceable_areas", serviceable_area_data)

    def get_serviceable_area_config(self) -> ServiceableAreas:
        """Retrieve serviceable area configurations from the store."""
        return self.get("serviceable_areas", self.serviceable_areas)

    def set_cab_config(self, cab_data: list):
        """Load cab configurations into the store."""
        self.cabs = cab_data
        self.set("cabs", cab_data)

    def get_cab_config(self) -> list:
        """Retrieve cab configurations from the store."""
        return self.get("cabs", self.cabs)

    def set_fuel_type_config(self, fuel_type_data: list):
        """Load fuel type configurations into the store."""
        self.fuel_types = fuel_type_data
        self.set("fuel_types", fuel_type_data)

    def get_fuel_type_config(self) -> list:
        """Retrieve fuel type configurations from the store."""
        return self.get("fuel_types", self.fuel_types)

    def set_trip_type_config(self, trip_type_data: list):
        """Load trip type configurations into the store."""
        self.trip_types = trip_type_data
        self.set("trip_types", trip_type_data)

    def get_trip_type_config(self) -> list:
        """Retrieve trip type configurations from the store."""
        return self.get("trip_types", self.trip_types)

    def populate_all_configs(
        self,
        pricing_data: Pricing,
        geography_data: Geographies,
        serviceable_area_data: ServiceableAreas,
        cab_data: list,
        fuel_type_data: list,
        trip_type_data: list,
    ):
        """Populate all configurations into the store."""
        self.set_pricing_config(pricing_data)
        self.set_geography_config(geography_data)
        self.set_serviceable_area_config(serviceable_area_data)
        self.set_cab_config(cab_data)
        self.set_fuel_type_config(fuel_type_data)
        self.set_trip_type_config(trip_type_data)

    def load_outstation_pricing_data(self, db: Session = Depends(get_mysql_session)):
        """Load outstation pricing data from the database into the store."""
        base_pricings = (
            db.query(OutstationCabPricing, CabType, FuelType)
            .join(CabType, OutstationCabPricing.cab_type_id == CabType.id)
            .join(FuelType, OutstationCabPricing.fuel_type_id == FuelType.id)
            .filter(
                OutstationCabPricing.is_available_in_network == True,
            )  # Ensure only available cabs are considered
            .all()
        )
