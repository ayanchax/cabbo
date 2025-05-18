import importlib
from core.config import settings


APP_NAME = "cabbo"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Backend API for cab booking platform."
APP_LOCALE= "en_IN.UTF-8"
APP_TIMEZONE = "UTC"
APP_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
APP_DATE_FORMAT = "%Y-%m-%d"
APP_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
APP_REGION = (settings.REGION).lower()


# Dynamically import country-specific settings
try:
    _region_settings = importlib.import_module(f"core.region_settings.{APP_REGION}")
except ImportError:
    raise ImportError(f"No region settings found for code: {APP_REGION}")
# Ensure the country settings module has the required attributes

# Expose country-specific settings as constants
APP_COUNTRY = _region_settings.COUNTRY
APP_COUNTRY_CODE = _region_settings.CODE
APP_COUNTRY_LANGUAGE = _region_settings.LANGUAGE
APP_COUNTRY_CURRENCY = _region_settings.CURRENCY
APP_COUNTRY_CURRENCY_SYMBOL = _region_settings.CURRENCY_SYMBOL
APP_CURRENCY_DECIMAL_PLACES = _region_settings.CURRENCY_DECIMAL_PLACES
APP_CURRENCY_FORMAT = _region_settings.CURRENCY_FORMAT
APP_CURRENCY_DECIMAL_SEPARATOR = _region_settings.CURRENCY_DECIMAL_SEPARATOR
APP_COUNTRY_PHONE_NUMBER_FORMAT = _region_settings.PHONE_NUMBER_FORMAT
APP_COUNTRY_PHONE_NUMBER_REGEX = _region_settings.PHONE_NUMBER_REGEX
APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR = _region_settings.PHONE_NUMBER_VALIIDATION_ERROR
APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE = _region_settings.PHONE_NUMBER_COUNTRY_CODE