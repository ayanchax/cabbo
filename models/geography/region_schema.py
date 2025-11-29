from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from core.security import RoleEnum
from models.map.location_schema import LocationInfo
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum, TripTypeEnum

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
    state_code: str = Field(..., description="ISO state code the region belongs to, e.g., 'KA' for Karnataka") # e.g. KA
    country_code: str = Field(..., description="ISO country code the region belongs to, e.g., 'IN' for India") # e.g. IN
    trip_types: Optional[List[TripTypeEnum]] = Field(
        None, description="List of supported trip types in the region"
    ) # Comma-separated list of trip types validated by TripTypeEnum
    fuel_types: Optional[List[FuelTypeEnum]] = Field(
        None, description="List of supported fuel types in the region"
    ) # Comma-separated list of fuel types validated by FuelTypeEnum
    car_types: Optional[List[CarTypeEnum]] = Field(
        None, description="List of supported car types in the region"
    ) # Comma-separated list of car types validated by CarTypeEnum
    airport_locations: Optional[List[LocationInfo]] = Field(
        None,
        description="Dictionary of airport locations with details like display name, lat, lng, place_id, address",
    ) # JSON string of airport locations validated by LocationInfo schema
    is_serviceable: Optional[bool] = Field(
        True, description="Indicates if the region is enabled for operations"
    )   

    class Config:
        from_attributes = True

class RegionUpdate(BaseModel):
    region_name: Optional[str] = Field(None, description="Name of the region/city") # e.g. Bangalore, Chennai
    region_alt_names: Optional[List[str]] = Field(
        None, description="List of alternative names for the region"
    )
    class Config:
        from_attributes = True
