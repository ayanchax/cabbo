from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
import re
from core.constants import (
    APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE,
    APP_COUNTRY_PHONE_NUMBER_REGEX,
    APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR,
)


class CustomerBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: str  # Initially during onboarding we just need a phone number, hence no optional

    @field_validator("phone_number")
    @classmethod
    def validate_and_sanitize_country_phone(cls, v):
        # Remove spaces and dashes
        v = v.replace(" ", "").replace("-", "")
        # If starts with +91, strip it for validation, but keep for storage
        if v.startswith(APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE):
            num = v[3:]
        else:
            num = v
        # Indian phone number: 10 digits, starts with 6-9
        if not re.fullmatch(APP_COUNTRY_PHONE_NUMBER_REGEX, num):
            raise ValueError(APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR)
        # Always store as +91XXXXXXXXXX
        return APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE + num


class CustomerCreate(CustomerBase):
    otp: str


class CustomerRead(CustomerBase):
    id: str = Field(..., description="UUID v4 customer ID")
    created_at: datetime

    class Config:
        from_attributes = True # Read from ORM attributes of customer_orm


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    # phone_number intentionally omitted to prevent updates


class CustomerOnboardInitiationRequest(BaseModel):
    phone_number: str

    @field_validator("phone_number")
    @classmethod
    def validate_and_sanitize_country_phone(cls, v):
        # Remove spaces and dashes
        v = v.replace(" ", "").replace("-", "")
        if v.startswith(APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE):
            num = v[3:]
        else:
            num = v
        if not re.fullmatch(APP_COUNTRY_PHONE_NUMBER_REGEX, num):
            raise ValueError(APP_COUNTRY_PHONE_NUMBER_VALIDATION_ERROR)
        return APP_COUNTRY_PHONE_NUMBER_COUNTRY_CODE + num

 