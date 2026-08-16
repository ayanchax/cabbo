from typing import Optional, Union
from core.exceptions import DATETIME_PROCESSING_ERROR, GENERIC_EXCEPTION, INVALID_DATETIME_INPUT, CabboException
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dateutil.parser import isoparse
from core.config import settings
import math
import requests
import re
import logging
from decimal import Decimal, ROUND_HALF_UP

log = logging.getLogger(__name__)


def validate_date_time(date_time: Union[str, datetime], timezone_str: str = None, utc_offset: int = None) -> Optional[datetime]:
    """
    Parse input (str or datetime). If naive, assume settings.CABBO_DEFAULT_TIMEZONE
    (fallback to UTC). Always return an aware datetime in UTC.
    """
    try:
        if not date_time:   
            return None  # Return None if date_time is None or empty
        if isinstance(date_time, str):
            try:
                dt = isoparse(date_time)
            except Exception as e:
                log.error(f"Error parsing datetime: {e}")
                if isinstance(date_time, datetime):
                    dt = date_time
                else:
                    raise CabboException("Invalid datetime format", status_code=400, error_code=INVALID_DATETIME_INPUT) from e
        elif isinstance(date_time, datetime):
            dt = date_time
        else:
            log.error(f"Invalid datetime type: {type(date_time)}")
            raise CabboException("Invalid datetime type", status_code=400, error_code=INVALID_DATETIME_INPUT)

        # If naive, attach tzinfo using utc_offset if provided, else use timezone_str/default
        if dt.tzinfo is None:
            if utc_offset is not None:
                # utc_offset is in minutes (preferred), fallback to hours if large
                if abs(utc_offset) > 24:
                    offset = timezone(timedelta(minutes=utc_offset))
                else:
                    offset = timezone(timedelta(hours=utc_offset))
                dt = dt.replace(tzinfo=offset)
            else:
                #Always prefer timezone_str if provided, else fallback to settings.CABBO_DEFAULT_TIMEZONE, and if that is not set then fallback to UTC
                tz_name = timezone_str or settings.CABBO_DEFAULT_TIMEZONE or "UTC"
                try:
                    local_tz = ZoneInfo(tz_name)
                except Exception as e:
                    log.error(f"Error setting timezone: {e}")
                    local_tz = timezone.utc
                dt = dt.replace(tzinfo=local_tz)
        # Always convert to UTC after enriching with timezone info
        return dt.astimezone(timezone.utc) # Return aware datetime in UTC
    except CabboException:
        raise
    except Exception as e:
        log.error(f"Error processing datetime: {e}")
        raise CabboException("Error processing datetime", status_code=400, error_code=DATETIME_PROCESSING_ERROR) from e


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

def calculate_age_from_dob(dob: date) -> int:
    """Calculate age from date of birth."""
    today = date.today()
    age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
    return age

def convert_based_on_currency(
    amount: float, conversion_factor: int, convert_to_lowest: bool = True
) -> float:
    """Convert the amount based on the currency's conversion factor.
    Args:
        amount (float): The original amount in standard currency units (e.g., rupees).
        conversion_factor (int): The conversion factor for the currency.
        convert_to_lowest (bool): Whether to convert to the lowest currency unit (default is True).
    Returns:
        float: The converted amount in the smallest currency unit (e.g., paise).
    """
    if conversion_factor and conversion_factor > 0:
        if convert_to_lowest:
            return amount * conversion_factor
        else:
            # If convert_to_lowest is False, it means we want to convert from the lowest unit to the standard unit, so we divide by the conversion factor
            return amount / conversion_factor
    else:
        log.error(
            f"Invalid conversion factor. Using original amount without conversion."
        )
        return amount
    
def safe_request(url, params=None, headers=None, timeout=3):
    try:
        response = requests.get(url, params=params, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        log.error(f"Request failed: {e}")
        return {}
    
def log_lru_cache(name, func):
    info = func.cache_info()
    log.debug(
        f"[CACHE:{name}] hits={info.hits}, misses={info.misses}, size={info.currsize}"
    )

def tokenize(text: str):
    return set(re.findall(r"\w+", text.lower()))

def round_value(val: float, precision: int = 4):
    return round(val, precision) if val is not None else None

def to_timezone_aware_datetime(dt:datetime):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

def format_trip_datetime(dt:datetime, timezone:str):
    trip_tz = ZoneInfo(timezone or "UTC")
    if not dt:
        return None

    # Database values represent UTC, even if MySQL returns them as naive.
    dt = as_utc_datetime(dt)

    return dt.astimezone(trip_tz)


def as_utc_datetime(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def format_duration_from_minutes(total_minutes: int) -> str:
    total_minutes = max(1, int(total_minutes))
    days, remaining_minutes = divmod(total_minutes, 1440) # 1 day = 1440 mins
    hours, minutes = divmod(remaining_minutes, 60) # 1 hour = 60 mins

    parts = []
    if days:
        parts.append(f"{days} {'day' if days == 1 else 'days'}")
    if hours:
        parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
    if minutes:
        parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")

    return " ".join(parts)

def format_duration_from_delta(delta: timedelta) -> str:
    total_minutes = math.ceil(delta.total_seconds() / 60)
    return format_duration_from_minutes(total_minutes)

def money(value: float) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
