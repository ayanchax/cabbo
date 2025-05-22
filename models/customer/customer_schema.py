from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
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


class CustomerBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: str  # Initially during onboarding we just need a phone number, hence no optional

    @field_validator("phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        return validate_and_sanitize_country_phone(v)


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

    @field_validator("phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        return validate_and_sanitize_country_phone(v)

