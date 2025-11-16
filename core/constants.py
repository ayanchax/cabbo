from models.geography.location_schema import LocationInfo


APP_NAME = "cabbo"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "Backend API for cab booking platform."
APP_LOCALE = "en_IN.UTF-8"
APP_TIMEZONE = "UTC"
APP_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
APP_DATE_FORMAT = "%Y-%m-%d"
APP_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
APP_ADMIN_EMAIL = "admin@cabbo.co.in"


## Country-specific settings
APP_COUNTRY = "India"
APP_COUNTRY_CODE = "IN"
APP_COUNTRY_LANGUAGE = "en"
APP_COUNTRY_CURRENCY = "INR"
APP_COUNTRY_CURRENCY_SYMBOL = "₹"
APP_CURRENCY_DECIMAL_PLACES = 2
APP_CURRENCY_FORMAT = "{:,.2f}"
APP_CURRENCY_DECIMAL_SEPARATOR = "."
APP_COUNTRY_PHONE_NUMBER_FORMAT = "+91XXXXXXXXXX"
APP_COUNTRY_PHONE_NUMBER_REGEX = r"[6-9]\d{9}"
APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR = (
    "Invalid Indian phone number. Must be 10 digits and start with 6-9."
)
APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE = "+91"
APP_COUNTRY_FLAG = "🇮🇳"
APP_COUNTRY_TIMEZONE = "Asia/Kolkata"
APP_HOME_CITY = "Bangalore"
APP_HOME_CITY_ALT = "Bengaluru"
APP_HOME_CITY_CODE = "BLR"
APP_HOME_STATE = "Karnataka"
APP_HOME_STATE_CODE = "KA"
APP_HOME_STATE_PERMIT_FEE = 0.0
APP_HOME_CITY_AIRPORT={
        "display_name":"Kempegowda International Airport, Bengaluru",
        "lat":13.1986,
        "lng":77.7066,
        "place_id":"ChIJL_P_CXMEDTkRw0ZdG-0GVvw", #official Mapbox place ID for the airport in Bengaluru
        "address":"Kempegowda International Airport, Devanahalli, Bengaluru, Karnataka 560300, India",
   
}
APP_AIRPORT_LOCATION = {
    APP_HOME_STATE: LocationInfo(
        **APP_HOME_CITY_AIRPORT
          )
}
