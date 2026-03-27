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