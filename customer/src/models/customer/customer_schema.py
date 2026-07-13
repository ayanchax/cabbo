from enum import Enum

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, Union
from datetime import datetime
from customer_api.src.models.common import S3ObjectInfo
from customer_api.src.models.user.user_enum import GenderEnum


class CustomerPayment(BaseModel):
    id: Optional[str] = None  # Customer ID, if available
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    contact: Optional[str] = None  # Contact number, can be phone or email

    @field_validator("email", mode="before")
    @classmethod
    def empty_email_as_none(cls, value):
        if value == "":
            return None
        return value

    class Config:
        exclude_none = True  # Exclude fields with None values from the model dump


class CustomerBase(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: str  # Initially during onboarding we just need a phone number, hence no optional
    dob: Optional[datetime] = None
    gender: Optional[GenderEnum] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    opt_in_updates: Optional[bool] = False
    s3_image_info: Optional[S3ObjectInfo] = (
        None  # To store S3 key and URL for profile picture if using S3 for storage
    )

     


class CustomerCreate(CustomerBase):
    pass
    # All other optional fields are inherited from CustomerBase


class CustomerRead(CustomerBase):
    id: str = Field(..., description="UUID v4 customer ID")
    created_at: datetime

    class Config:
        from_attributes = True  # Read from ORM attributes of customer_orm

class CustomerSafeRead(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: str  # Initially during onboarding we just need a phone number, hence no optional
    # emergency_contact_name: Optional[str] = None -- We will expose this field for emergency contact name in v2.
    # emergency_contact_number: Optional[str] = None -- We will expose this field for emergency contact number in v2.
    # opt_in_updates: Optional[bool] = False -- We will expose this field for enabling customer to opt in to receive promotional whatsapp updates in v2.
    profile_picture_url: Optional[str] = None  # Customer's profile picture url
    is_email_verified: Optional[bool] = False  # To indicate if the customer's email is verified
    joined_on: Optional[datetime] = None  # To indicate when the customer joined the platform
    number_of_trips: Optional[int] = 0  # To indicate how many trips the customer has taken
    can_reinitiate_email_verification: Optional[bool] = False  # To indicate if the customer can initiate email verification
    class Config:
        from_attributes = True 
        extra="ignore"




class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    dob: Optional[datetime] = None
    gender: Optional[GenderEnum] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    opt_in_updates: Optional[bool] = None

    # phone_number intentionally omitted to prevent updates



class CustomerReadAfterUpdate(CustomerUpdate):
    last_modified: datetime

    class Config:
        from_attributes = True  # Read from ORM attributes of customer_orm


class CustomerOTPRequest(BaseModel):
    phone_number: str
    otp:Optional[str] = None  # OTP is optional here because for resend OTP endpoint, we might not require it in the payload
    

class ClientAccessToken(BaseModel):
    existing_token: Optional[str] = None  # Token is optional here because for some endpoints, we might not require it in the payload

class CustomerOnboardInitiationRequest(ClientAccessToken):
    phone_number: str
    



class CustomerLoginRequest(BaseModel):
    phone_number: str
    otp: str


class CustomerLoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    first_time_login: Optional[bool] = None


class CustomerSuspensionRequest(BaseModel):
    customer_id: Optional[str] = None
    reason: Optional[str] = None
