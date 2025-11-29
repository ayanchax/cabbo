from pydantic import BaseModel
from models.geography.country_schema import CountrySchema
from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema




class Geographies(BaseModel):
    regions: dict[str, RegionSchema] = {}  # region_code -> RegionSchema
    states: dict[str, StateSchema] = {}  # state_code -> StateSchema
    countries: dict[str, CountrySchema] = {}  # country_code -> CountrySchema
