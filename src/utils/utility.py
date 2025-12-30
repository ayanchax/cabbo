from typing import Union
from core.exceptions import CabboException
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dateutil.parser import isoparse
from core.config import settings


def validate_date_time(date_time: Union[str, datetime]):
    """
    Parse input (str or datetime). If naive, assume settings.CABBO_DEFAULT_TIMEZONE
    (fallback to UTC). Always return an aware datetime in UTC.
    """
    try:
        if isinstance(date_time, str):
            try:
                dt = isoparse(date_time)
            except Exception as e:
                raise CabboException("Invalid datetime format", status_code=400) from e
        elif isinstance(date_time, datetime):
            dt = date_time
        else:
            raise CabboException("Invalid datetime type", status_code=400)

        # If naive, attach configured default tz (e.g., "Asia/Kolkata"), then convert to UTC
        if dt.tzinfo is None:
            tz_name = getattr(settings, "CABBO_DEFAULT_TIMEZONE", "UTC")
            try:
                local_tz = ZoneInfo(tz_name)
            except Exception:
                local_tz = timezone.utc
            dt = dt.replace(tzinfo=local_tz)
        # Always convert to UTC
        return dt.astimezone(timezone.utc)
    except Exception as e:
        raise CabboException("Error processing datetime", status_code=400) from e


def remove_none_recursive(obj):
    if isinstance(obj, dict):
        return {k: remove_none_recursive(v) for k, v in obj.items() if v is not None}
    elif isinstance(obj, list):
        return [remove_none_recursive(v) for v in obj if v is not None]
    else:
        return obj


def transform_datetime_to_str(obj):
    if isinstance(obj, dict):
        return {k: transform_datetime_to_str(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [transform_datetime_to_str(v) for v in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    else:
        return obj

    """Format currency according to country preferences."""
    # Format with thousand separator
    formatted = f"{amount:,.2f}"
    return f"{country.currency_symbol}{formatted}"
