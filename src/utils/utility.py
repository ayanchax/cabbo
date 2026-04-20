from typing import Union
from core.exceptions import CabboException
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from dateutil.parser import isoparse
from core.config import settings
import requests
import re


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
        return dt.astimezone(timezone.utc) # Return aware datetime in UTC
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
        print(
            f"Invalid conversion factor. Using original amount without conversion."
        )
        return amount
    
def safe_request(url, params, timeout=3):
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Request failed: {e}")
        return {}
    
def log_lru_cache(name, func):
    info = func.cache_info()
    print(
        f"[CACHE:{name}] hits={info.hits}, misses={info.misses}, size={info.currsize}"
    )

def tokenize(text: str):
    return set(re.findall(r"\w+", text.lower()))
    


