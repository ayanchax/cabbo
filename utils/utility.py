import re
from typing import Union
from core.exceptions import CabboException
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from dateutil.parser import isoparse
from core.config import settings
from models.geography.country_schema import CountrySchema


def validate_phone_by_country(phone: str, country: CountrySchema) -> str:
    """
    Validate and sanitize phone number based on country configuration.
    
    Args:
        phone: Phone number to validate
        country: Country configuration from ConfigStore
    
    Returns:
        Sanitized phone number with country code
    """
    # Remove spaces, hyphens, parentheses
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    
    # Extract number without country code
    if phone.startswith(country.phone_code):
        num = phone[len(country.phone_code):]
    elif phone.startswith('+'):
        # Remove any country code
        num = re.sub(r'^\+\d+', '', phone)
    else:
        num = phone
    
    # Validate length
    if len(num) < country.phone_min_length or len(num) > country.phone_max_length:
        raise CabboException(
            f"Invalid phone number. Expected {country.phone_min_length}-{country.phone_max_length} digits"
            + (f". Example: {country.phone_example}" if country.phone_example else "+<country code>XXXXXXXXXX"),
            status_code=422
        )
    
    # Validate regex
    if not re.fullmatch(country.phone_regex, num):
        raise CabboException(
            f"Invalid phone number format for {country.name}"
            + (f". Example: {country.phone_example}" if country.phone_example else "+<country code>XXXXXXXXXX"),
            status_code=422
        )
    
    return country.phone_code + num


def validate_postal_code_by_country(postal_code: str, country: CountrySchema) -> str:
    """Validate postal code based on country configuration."""
    postal_code = postal_code.strip().upper()
    
    if not re.fullmatch(country.postal_code_regex, postal_code):
        raise CabboException(
            f"Invalid postal code format for {country.name}",
            status_code=422
        )
    
    return postal_code


def validate_driver_age_by_country(age: int, country: CountrySchema):
    """Validate driver age based on country rules."""
    if age < country.min_age_for_drivers:
        raise CabboException(
            f"Minimum age for driver in {country.country_name} is {country.min_age_for_drivers}",
            status_code=422
        )


def validate_customer_age_by_country(age: int, country: CountrySchema):
    """Validate customer age based on country rules."""
    if age < country.min_age_for_customers:
        raise CabboException(
            f"Minimum age for customer in {country.country_name} is {country.min_age_for_customers}",
            status_code=422
        )

def validate_system_user_age_by_country(age: int, country: CountrySchema):
    """Validate system user age based on country rules."""
    if age < country.min_age_for_system_users:
        raise CabboException(
            f"Minimum age for system user in {country.country_name} is {country.min_age_for_system_users}",
            status_code=422
        )

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