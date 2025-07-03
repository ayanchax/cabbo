from datetime import datetime
import re
from typing import Union
from core.constants import (
    APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE,
    APP_COUNTRY_PHONE_NUMBER_REGEX,
    APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR,
)
from core.exceptions import CabboException


def validate_and_sanitize_country_phone(v):
    v = v.replace(" ", "").replace("-", "")
    if v.startswith(APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE):
        num = v[3:]
    else:
        num = v
    if not re.fullmatch(APP_COUNTRY_PHONE_NUMBER_REGEX, num):
        raise CabboException(APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR, status_code=422)
    return APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE + num


def validate_date_time(date_time: Union[str, datetime]):
    """
    Validates and sanitizes a date-time string to ensure it is in ISO 8601 format.
    If the input is already in the correct format, it returns the string unchanged.
    If not, it raises a ValueError.
    """
    try:
        output = (
            date_time
            if isinstance(date_time, datetime)
            else datetime.fromisoformat(str(date_time))
        )
        return output

    except Exception:
        raise CabboException(
            "Invalid date_time format. Must be ISO datetime string.",
            status_code=400,
        )
