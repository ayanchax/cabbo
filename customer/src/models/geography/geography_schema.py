from pydantic import BaseModel, Field
from typing import Dict, Optional
from customer_api.src.models.geography.country_schema import CountrySchema
from customer_api.src.models.geography.state_schema import StateSchema
from customer_api.src.models.geography.region_schema import RegionSchema


class Geographies(BaseModel):
    countries: Dict[str, CountrySchema] = Field(
        default_factory=dict,
        description="Dictionary of countries keyed by country_code"
    )
    states: Dict[str, StateSchema] = Field(
        default_factory=dict,
        description="Dictionary of states keyed by state_code"
    )
    regions: Dict[str, RegionSchema] = Field(
        default_factory=dict,
        description="Dictionary of regions keyed by region_code"
    )

    country_server:Optional[CountrySchema] = Field(
        None,
        description="Country configuration for the server's operating country"
    )

    