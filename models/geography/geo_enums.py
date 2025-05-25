from pydantic import BaseModel
from typing import Optional


class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None
