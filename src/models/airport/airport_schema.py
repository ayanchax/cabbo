from pydantic import BaseModel
from typing import Optional


class AirportSchema(BaseModel):
    id: Optional[str] = None
    display_name: str
    iata_code: Optional[str] = None
    icao_code: Optional[str] = None
    elevation_ft: Optional[int] = None
    timezone: Optional[str] = None
    dst: Optional[str] = None
    tz_database_time_zone: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    place_id: str
    address: str
    country: Optional[str] = None
    country_code: Optional[str] = None
    state: Optional[str] = None
    state_code: Optional[str] = None
    region: Optional[str] = None
    region_code: str
    postal_code: Optional[str] = None
    is_serviceable: Optional[bool] = True
    provider: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "allow"


class AirportUpdateSchema(BaseModel):
    id: Optional[str] = None
    display_name: Optional[str] = None
    iata_code: Optional[str] = None
    icao_code: Optional[str] = None
    elevation_ft: Optional[int] = None
    timezone: Optional[str] = None
    dst: Optional[str] = None
    tz_database_time_zone: Optional[str] = None
    type: Optional[str] = None
    source: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "allow"
