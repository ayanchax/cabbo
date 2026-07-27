from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MobilityHub(str, Enum):
    """Classifies a location as a mobility establishment (airport, station, etc.)."""
    airport = "airport"
    railway_station = "railway_station"
    bus_station = "bus_station"
    taxi_stand = "taxi_stand"
    transit_station = "transit_station"   # generic: metro, tram, etc.
    subway_station = "subway_station"


class LocationInfo(BaseModel):
    display_name: Optional[str] = None
    lat: Optional[float]=None
    lng: Optional[float]=None
    place_id: Optional[str] = None
    address: Optional[str] = None

    # ✅ Add structured geography fields (populated by Location provider)
    country: Optional[str] = Field(None, description="Country name from Location provider")
    country_code: Optional[str] = Field(None, description="ISO country code (e.g., IN, US)")
    state: Optional[str] = Field(None, description="State/province name")
    state_code: Optional[str] = Field(None, description="State code (e.g., KA, TN)")
    region: Optional[str] = Field(None, description="City/region name")
    region_code: Optional[str] = Field(None, description="Region code (e.g., BLR, MYS)")
    postal_code: Optional[str] = Field(None, description="Postal/ZIP code")
    mobility_hub: Optional[MobilityHub] = Field(None, description="Mobility establishment type (airport, railway station, etc.) — populated from Google place types")
    class Config:
        extra="allow"
        exclude_none = True  # Exclude fields with None values from the model dump
         



class Address(BaseModel):
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    country_id: Optional[str] = Field(None, description="Country identifier")
    region_id: Optional[str] = Field(None, description="Region identifier")
    state_id: Optional[str] = Field(None, description="State identifier")
    state: Optional[str] = Field(None, description="State or province name")
    country: Optional[str] = Field(None, description="Country name")
    landmark: Optional[str] = Field(None, description="Landmark near the address")
    postal_code: Optional[str] = Field(None, description="Postal or ZIP code")

class LocationProximity(BaseModel):
    lat: float
    lng: float
    radius_km: Optional[float] = Field(50, description="Radius in kilometers to bias location suggestions")


class MapUrl(BaseModel):
    place_id: str = Field(..., description="Maps place ID")
    map_url: str = Field(..., description="Maps URL for the place")
