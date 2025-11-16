from pydantic import BaseModel, Field
from typing import List, Optional

class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None

class CountrySchema(BaseModel):
    country_name: str = Field(..., description="Full name of the country")
    country_code: str = Field(..., description="ISO country code, e.g., 'IN' for India")
    currency: str = Field(..., description="Currency code, e.g., 'INR' for Indian Rupee")
    currency_symbol: str = Field(..., description="Symbol of the currency, e.g., '₹'")
    flag: str = Field(..., description="Emoji flag of the country")
    time_zone: str = Field(..., description="Primary time zone of the country")
    locale: str = Field(..., description="Locale code, e.g., 'en_IN'")
    supported_regions: Optional[List[str]] = Field(
        None, description="List of supported region codes within the country"
    )

    class Config:
        from_attributes = True

class RegionSchema(BaseModel):
    region_name: str = Field(..., description="Name of the region/city")
    region_display_name: str = Field(..., description="Display name of the region/city")
    region_state: str = Field(..., description="State in which the region is located")
    region_state_code: str = Field(..., description="State code, e.g., 'KA' for Karnataka")
    region_code: str = Field(..., description="Region code, e.g., 'BLR' for Bangalore")
    airport_codes: Optional[List[str]] = Field(
        None, description="List of airport codes associated with the region"
    )
    supported_trip_types: Optional[List[str]] = Field(
        None, description="List of supported trip types in the region"
    )
    supported_fuel_types: Optional[List[str]] = Field(
        None, description="List of supported fuel types in the region"
    )
    supported_car_types: Optional[List[str]] = Field(
        None, description="List of supported car types in the region"
    )
    airport_locations: Optional[dict[str, LocationInfo]] = Field(
        None,
        description="Dictionary of airport locations with details like display name, lat, lng, place_id, address",
    )

    class Config:
        from_attributes = True