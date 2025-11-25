from pydantic import BaseModel, Field
from typing import List, Optional

from models.geography.country_schema import CountrySchema
from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema

class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None


class Geographies(BaseModel):
    regions: dict[str, RegionSchema] = {}  # region_code -> RegionSchema
    states: dict[str, StateSchema] = {}  # state_code -> StateSchema
    countries: dict[str, CountrySchema] = {}  # country_code -> CountrySchema
