from pydantic import BaseModel, Field
from typing import Dict
from models.geography.country_schema import CountrySchema
from models.geography.state_schema import StateSchema
from models.geography.region_schema import RegionSchema


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