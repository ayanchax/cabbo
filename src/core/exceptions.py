import traceback
from typing import Any, Optional, Union
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

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



def get_mysql_exception(e: Exception) -> "CabboException":
    if isinstance(e, IntegrityError):
        orig = getattr(e, "orig", None)
        mysql_code = getattr(orig, "errno", None)
        if mysql_code == 1062:
            msg = str(orig)
            field = msg.split("key '")[-1].rstrip("'") if "key '" in msg else "field"
            return CabboException(f"Duplicate entry for {field}.", error_code="DUPLICATE_ENTRY", status_code=409)
        if mysql_code == 1452:
            return CabboException("Referenced record does not exist.", error_code="FOREIGN_KEY_VIOLATION", status_code=400)
        if mysql_code == 1048:
            return CabboException("A required field cannot be null.", error_code="NULL_CONSTRAINT_VIOLATION", status_code=400)
        return CabboException(str(orig or e), error_code="INTEGRITY_ERROR", status_code=400)
    if isinstance(e, OperationalError):
        return CabboException("A database operational error occurred.", error_code="DB_OPERATIONAL_ERROR", status_code=503)
    return CabboException(str(e), error_code="DB_ERROR", status_code=500)