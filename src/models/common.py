from enum import Enum
from typing import Any, Callable, Dict

from pydantic import BaseModel


class AppBackgroundTask(BaseModel):
    fn: Callable
    kwargs: Dict[str, Any]

class FlagsEnum(str, Enum):
    flagged="flagged"
    unflagged="unflagged"
    none="none"

class AmenitiesSchema(BaseModel):
    ac: bool = True  # Air conditioning
    music_system: bool = True  # Music system
    water_bottle: bool = False  # Water bottle
    tissues: bool = False  # Tissues
    candies: bool = False  # Candies
    snacks: bool = False  # Snacks
    phone_charger: bool = False  # Phone charger
    aux_cable: bool = False  # Aux cable for music
    bluetooth: bool = False  # Bluetooth connectivity
    wifi: bool = False  # Wifi connectivity