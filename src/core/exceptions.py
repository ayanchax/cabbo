import traceback
from typing import Any, Optional, Union

class CabboException(Exception):
    """
    Custom exception for Cabbo application errors.
    Optionally accepts a message, a status code, and a stack trace.
    """
    def __init__(self, message: Union[str, dict[str, Any]], error_code: Optional[str] = None, status_code: int = 400, include_traceback: bool = False):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code
        self.traceback = None
        if include_traceback:
            self.traceback = traceback.format_exc()

    def __str__(self):
        base = f"{self.message} (status_code={self.status_code})"
        if self.traceback and self.traceback != 'NoneType: None\n':
            return f"{base}\nStack trace:\n{self.traceback}"
        return base
