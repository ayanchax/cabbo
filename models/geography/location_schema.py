from pydantic import BaseModel, Field
from typing import List, Optional

class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None


