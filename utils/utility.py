import re
from core.constants import (
    APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE,
    APP_COUNTRY_PHONE_NUMBER_REGEX,
    APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR,
)


def validate_and_sanitize_country_phone(v):
    v = v.replace(" ", "").replace("-", "")
    if v.startswith(APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE):
        num = v[3:]
    else:
        num = v
    if not re.fullmatch(APP_COUNTRY_PHONE_NUMBER_REGEX, num):
        raise ValueError(APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR)
    return APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE + num
