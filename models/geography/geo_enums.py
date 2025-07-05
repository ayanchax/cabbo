from pydantic import BaseModel
from typing import Optional
from core.constants import APP_HOME_CITY_AIRPORT, APP_HOME_STATE


class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None


APP_AIRPORT_LOCATION = {
    APP_HOME_STATE: LocationInfo(
        **APP_HOME_CITY_AIRPORT
          )
}
