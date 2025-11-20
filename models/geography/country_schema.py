from typing import List, Optional
from pydantic import BaseModel, Field

from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema


class CountrySchema(BaseModel):
    country_name: str = Field(..., description="Full name of the country") # e.g. India
    country_code: str = Field(..., description="ISO country code, e.g., 'IN' for India") # e.g. IN
    phone_code: str = Field(..., description="International phone code, e.g., '+91' for India") # e.g. +91
    currency: str = Field(..., description="Currency code, e.g., 'INR' for Indian Rupee") # e.g. INR
    currency_symbol: str = Field(..., description="Symbol of the currency, e.g., '₹'") # e.g. ₹
    flag: str = Field(..., description="Emoji flag of the country") # e.g. 🇮🇳
    time_zone: str = Field(..., description="Primary time zone of the country") # e.g. Asia/Kolkata
    locale: str = Field(..., description="Locale code, e.g., 'en_IN'") # e.g. en_IN
    states: Optional[List["StateSchema"]] = Field(None, description="List of states within the country") # List of states
    regions: Optional[List["RegionSchema"]] = Field(None, description="List of regions within the country") # List of regions
    
    class Config:
        from_attributes = True
