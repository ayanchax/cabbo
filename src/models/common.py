from typing import Any, Callable, Dict

from pydantic import BaseModel


class AppBackgroundTask(BaseModel):
    fn: Callable
    kwargs: Dict[str, Any]