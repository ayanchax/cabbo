from typing import Optional

from pydantic import BaseModel, Field


class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None

class Address(BaseModel):
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    country_id: Optional[str] = Field(None, description="Country identifier")
    region_id: Optional[str] = Field(None, description="Region identifier")
    state_id: Optional[str] = Field(None, description="State identifier")
    postal_code: Optional[str] = Field(None, description="Postal or ZIP code")