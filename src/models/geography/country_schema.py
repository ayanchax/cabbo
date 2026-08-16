from typing import List, Optional
from pydantic import BaseModel, Field

from models.geography.region_schema import RegionSchema
from models.geography.state_schema import StateSchema


class CountrySchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the country")
    country_name: str = Field(..., description="Full name of the country")  # e.g. India
    country_code: str = Field(
        ..., description="ISO country code, e.g., 'IN' for India"
    )  # e.g. IN
    phone_code: str = Field(
        ..., description="International phone code, e.g., '+91' for India"
    )  # e.g. +91
    phone_min_length: Optional[int] = Field(
        10, description="Minimum length of phone number without country code"
    )  # e.g. 10
    phone_max_length: Optional[int] = Field(
        10, description="Maximum length of phone number without country code"
    )  # e.g. 10
    phone_regex: Optional[str] = Field(
        "^[6-9]\d{9}$", description="Regex pattern to validate phone numbers"
    )  # e.g. "^[6-9]\d{9}$"
    phone_example: Optional[str] = Field(
        None, description="Example phone number without country code"
    )  # e.g. 9876543210
    postal_code_regex: Optional[str] = Field(
        "^\d{6}$", description="Regex pattern to validate postal codes"
    )  # e.g. "^\d{6}$"
    distance_unit: Optional[str] = Field(
        "km", description="Unit of distance measurement, e.g., 'km' or 'miles'"
    )  # e.g. km
    currency: str = Field(
        ..., description="Currency code, e.g., 'INR' for Indian Rupee"
    )  # e.g. INR
    currency_symbol: str = Field(
        ..., description="Symbol of the currency, e.g., '₹'"
    )  # e.g. ₹
    currency_decimal_places: Optional[int] = Field(
        2, description="Number of decimal places, e.g., 2 for paise in INR"
    )  # e.g. 2 for paise in INR
    currency_in_words: Optional[str] = Field(
        "Rupees", description="Currency in words, e.g., 'Rupees'"
    )  # e.g. Rupees
    currency_international_name: Optional[str] = Field(
        "Indian Rupee", description="International name, e.g., 'Indian Rupee'"
    )  # e.g. Indian Rupee
    currency_symbol_position: Optional[str] = Field(
        "before",
        description="Position of the currency symbol, e.g., 'before' or 'after'",
    )  # whether currency symbol is placed before or after the amount, e.g. ₹100 or 100¥
    currency_code_position: Optional[str] = Field(
        "after", description="Position of the currency code, e.g., 'before' or 'after'"
    )  # whether currency code is placed before or after the amount, e.g. 100 INR or USD 100
    currency_thousand_separator: Optional[str] = Field(
        ",", description="Thousand separator, e.g., ','"
    )  # e.g. 1,00,000
    currency_decimal_separator: Optional[str] = Field(
        ".", description="Decimal separator, e.g., '.'"
    )  # e.g. 100.50
    currency_lowest_unit_name: Optional[str] = Field(
        "Paise", description="Name of the lowest currency unit, e.g., 'Paise'"
    )  # e.g. Paise
    currency_lowest_unit_conversion_factor: Optional[int] = Field(
        100,
        description="Conversion factor for the lowest currency unit, e.g., 100 (1 Rupee = 100 Paise)",
    )  # e.g. 100 (1 Rupee = 100 Paise)
    flag: str = Field(..., description="Emoji flag of the country")  # e.g. 🇮🇳
    time_zone: str = Field(
        ..., description="Primary time zone of the country"
    )  # e.g. Asia/Kolkata
    locale: str = Field(..., description="Locale code, e.g., 'en_IN'")  # e.g. en_IN
    states: Optional[List["StateSchema"]] = Field(
        None, description="List of states within the country"
    )  # List of states
    regions: Optional[List["RegionSchema"]] = Field(
        None, description="List of regions within the country"
    )  # List of regions
    is_serviceable: Optional[bool] = Field(
        True, description="Indicates if the country is enabled for operations"
    )
    min_age_for_drivers: Optional[int] = Field(
        18, description="Minimum age required to register as a driver in this country"
    )
    min_age_for_customers: Optional[int] = Field(
        13, description="Minimum age required to register as a customer in this country"
    )
    max_age_for_drivers: Optional[int] = Field(
        90, description="Maximum age limit to register as a driver in this country"
    )
    max_age_for_customers: Optional[int] = Field(
        90, description="Maximum age limit to register as a customer in this country"
    )
    min_age_for_system_users: Optional[int] = Field(
        18,
        description="Minimum age required to register as a system user in this country",
    )
    max_age_for_system_users: Optional[int] = Field(
        90, description="Maximum age limit to register as a system user in this country"
    )
    is_default: Optional[bool] = Field(
        False,
        description="Indicates if this country is the default country for the platform",
    )

    class Config:
        from_attributes = True


class CountryReadSchema(BaseModel):
    country_name: str = Field(..., description="Full name of the country")  # e.g. India
    country_code: str = Field(
        ..., description="ISO country code, e.g., 'IN' for India"
    )  # e.g. IN
    phone_code: str = Field(
        ..., description="International phone code, e.g., '+91' for India"
    )  # e.g. +91
    
    
    currency_code: str = Field(
    ..., validation_alias="currency", description="Currency code, e.g., 'INR' for Indian Rupee"
)  # e.g. INR
    currency_symbol: str = Field(
        ..., description="Symbol of the currency, e.g., '₹'"
    )  # e.g. ₹
    currency_decimal_places: Optional[int] = Field(
        2, description="Number of decimal places, e.g., 2 for paise in INR"
    )  # e.g. 2 for paise in INR
    
    currency_lowest_unit_conversion_factor: Optional[int] = Field(
        100,
        description="Conversion factor for the lowest currency unit, e.g., 100 (1 Rupee = 100 Paise)",
    )  # e.g. 100 (1 Rupee = 100 Paise)
    flag: str = Field(..., description="Emoji flag of the country")  # e.g. 🇮🇳
    time_zone: str = Field(
        ..., description="Primary time zone of the country"
    )  # e.g. Asia/Kolkata
    locale: str = Field(..., description="Locale code, e.g., 'en_IN'")  # e.g. en_IN

    class Config:
        from_attributes = True
        extra="ignore"

class CountryUpdateSchema(BaseModel):
    id: str = Field(..., description="Unique identifier for the country")
    country_name: Optional[str] = Field(
        None, description="Full name of the country"
    )  # e.g. India
    country_code: Optional[str] = Field(
        None, description="ISO country code, e.g., 'IN' for India"
    )  # e.g. IN
    phone_code: Optional[str] = Field(
        None, description="International phone code, e.g., '+91' for India"
    )  # e.g. +91
    phone_min_length: Optional[int] = Field(
        10, description="Minimum length of phone number without country code"
    )  # e.g. 10
    phone_max_length: Optional[int] = Field(
        10, description="Maximum length of phone number without country code"
    )  # e.g. 10
    phone_regex: Optional[str] = Field(
        "^[6-9]\d{9}$", description="Regex pattern to validate phone numbers"
    )  # e.g. "^[6-9]\d{9}$"
    phone_example: Optional[str] = Field(
        None, description="Example phone number without country code"
    )  # e.g. 9876543210
    postal_code_regex: Optional[str] = Field(
        "^\d{6}$", description="Regex pattern to validate postal codes"
    )  # e.g. "^\d{6}$"
    distance_unit: Optional[str] = Field(
        "km", description="Unit of distance measurement, e.g., 'km' or 'miles'"
    )  # e.g. km
    currency: Optional[str] = Field(
        None, description="Currency code, e.g., 'INR' for Indian Rupee"
    )  # e.g. INR
    currency_symbol: Optional[str] = Field(
        None, description="Symbol of the currency, e.g., '₹'"
    )  # e.g. ₹
    flag: Optional[str] = Field(
        None, description="Emoji flag of the country"
    )  # e.g. 🇮🇳
    time_zone: Optional[str] = Field(
        None, description="Primary time zone of the country"
    )  # e.g. Asia/Kolkata
    locale: Optional[str] = Field(
        None, description="Locale code, e.g., 'en_IN'"
    )  # e.g. en_IN

    min_age_for_drivers: Optional[int] = Field(
        18, description="Minimum age required to register as a driver in this country"
    )
    min_age_for_customers: Optional[int] = Field(
        13, description="Minimum age required to register as a customer in this country"
    )
    max_age_for_drivers: Optional[int] = Field(
        90, description="Maximum age limit to register as a driver in this country"
    )
    max_age_for_customers: Optional[int] = Field(
        90, description="Maximum age limit to register as a customer in this country"
    )
    min_age_for_system_users: Optional[int] = Field(
        18,
        description="Minimum age required to register as a system user in this country",
    )
    max_age_for_system_users: Optional[int] = Field(
        90, description="Maximum age limit to register as a system user in this country"
    )

    class Config:
        from_attributes = True
