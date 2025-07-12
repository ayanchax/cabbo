from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
from utils.utility import validate_and_sanitize_country_phone
from enum import Enum


class GenderEnum(str, Enum):
    male = "male"
    female = "female"
    transgender = "transgender"
    prefer_not_to_disclose = "prefer_not_to_disclose"


class CustomerPayment(BaseModel):
    id: Optional[str] = None  # Customer ID, if available
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    contact: Optional[str] = None  # Contact number, can be phone or email

    @field_validator("contact", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)

class CustomerBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: str  # Initially during onboarding we just need a phone number, hence no optional
    dob: Optional[datetime] = None
    # age is not accepted directly, calculated from dob
    age: Optional[int] = None
    gender: Optional[GenderEnum] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    opt_in_updates: Optional[bool] = False

    @field_validator("phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        return validate_and_sanitize_country_phone(v)

    @field_validator("emergency_contact_number", mode="before")
    @classmethod
    def emergency_contact_number_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)


class CustomerCreate(CustomerBase):
    otp: str

    # All other optional fields are inherited from CustomerBase


class CustomerRead(CustomerBase):
    id: str = Field(..., description="UUID v4 customer ID")
    created_at: datetime

    class Config:
        from_attributes = True  # Read from ORM attributes of customer_orm


class CustomerReadWithProfilePicture(CustomerRead):
    image_url: str = Field(None, description="URL to the customer's profile picture")

    class Config:
        from_attributes = True  # Read from ORM attributes of customer_orm


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    dob: Optional[datetime] = None
    gender: Optional[GenderEnum] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    opt_in_updates: Optional[bool] = None

    # phone_number intentionally omitted to prevent updates

    @field_validator("emergency_contact_number", mode="before")
    @classmethod
    def emergency_contact_number_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)


class CustomerReadProfilePictureAfterUpdate(BaseModel):
    image_url: str = Field(None, description="URL to the customer's profile picture")
    last_modified: datetime = Field(
        None, description="Last modified date of the customer profile"
    )


class CustomerReadAfterUpdate(CustomerUpdate):
    last_modified: datetime

    class Config:
        from_attributes = True  # Read from ORM attributes of customer_orm


class CustomerOnboardInitiationRequest(BaseModel):
    phone_number: str

    @field_validator("phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        return validate_and_sanitize_country_phone(v)


class CustomerLoginRequest(BaseModel):
    phone_number: str
    otp: str

    @field_validator("phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        return validate_and_sanitize_country_phone(v)


class CustomerLoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    customer_id: str
    first_time_login: Optional[bool] = None
