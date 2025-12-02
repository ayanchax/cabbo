import json
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Union
from datetime import datetime
from core.security import RoleEnum
from models.map.location_schema import LocationInfo

# Region is a city or metro area within a state or province within a country
# Region is the smallest geography unit for trip operations, all other geographies (State, Country) are linked via foreign keys
# Any kind of granular service area definition (trip wise service availability, 'trip-cab-fuel' wise pricing, airport boundaries, fuel type support, cab type availability etc.) are mapped at the lowest level i.e, regions

class RegionBase(BaseModel):
    region_state: str
    region_state_code: str


class RegionCreate(RegionBase):
    pass


class RegionOut(RegionBase):
    id: str
    created_by: RoleEnum
    created_at: Optional[datetime]
    last_modified: Optional[datetime]

    class Config:
        from_attributes = True

class RegionSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the region")  # UUID
    # Region is a city or metro area within a state or province within a country
    region_name: str = Field(..., description="Name of the region/city") # e.g. Bangalore, Chennai
    region_code: str = Field(..., description="Region code, e.g., 'BLR' for Bangalore") # e.g. BLR, MAA
    region_alt_names: Optional[List[str]] = Field(
        None, description="List of alternative names for the region"
    )  # e.g. ["Bengaluru", "Bangalore City"]
    country_code: Optional[str] = Field(None, description="ISO country code the region belongs to, e.g., 'IN' for India") # e.g. IN
    state_code: Optional[str] = Field(None, description="ISO state code the region belongs to, e.g., 'KA' for Karnataka") # e.g. KA
    country_id: Optional[str] = Field(None, description="UUID of the country this region belongs to")  # UUID of the country
    state_id: Optional[str] = Field(None, description="UUID of the state this region belongs to")  # UUID of the state
    trip_types: Optional[List[str]] = Field(
        None, description="List of supported trip types in the region" 
    )  
    fuel_types: Optional[List[str]] = Field(
        None, description="List of supported fuel types in the region"
    )  
    car_types: Optional[List[str]] = Field(
        None, description="List of supported car types in the region"
    )  
    airport_locations: Optional[List[dict]] = Field(
        None,
        description="Dictionary of airport locations with details like display name, lat, lng, place_id, address",
    ) # JSON string of airport locations validated by LocationInfo schema
    is_serviceable: Optional[bool] = Field(
        True, description="Indicates if the region is enabled for operations"
    )   

    class Config:
        from_attributes = True
    
    @field_validator('region_alt_names', 'trip_types', 'fuel_types', 'car_types', mode='before')
    @classmethod
    def parse_json_list_fields(cls, v):
        """Parse JSON string fields to lists."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v
    
    @field_validator('airport_locations', mode='before')
    @classmethod
    def parse_airport_locations(cls, v):
        """Parse airport_locations if it's a JSON string."""
        if v is None:
            return None
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return None
        return v

class RegionUpdate(BaseModel):
    region_name: Optional[str] = Field(None, description="Name of the region/city") # e.g. Bangalore, Chennai
    region_alt_names: Optional[List[str]] = Field(
        None, description="List of alternative names for the region"
    )
    class Config:
        from_attributes = True
