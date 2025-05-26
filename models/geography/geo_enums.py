from pydantic import BaseModel
from typing import Optional
from core.constants import APP_HOME_STATE


class LocationInfo(BaseModel):
    display_name: str
    lat: float
    lng: float
    place_id: Optional[str] = None
    address: Optional[str] = None


APP_AIRPORT_LOCATION = {
    APP_HOME_STATE: LocationInfo(
        display_name="Kempegowda International Airport, Bengaluru",
        lat=13.1986,
        lng=77.7066,
        place_id="ChIJLwPMoJmVrjsR4E9-UejD3_g",
        address="Kempegowda International Airport, Devanahalli, Bengaluru, Karnataka 560300, India",
    )
}
