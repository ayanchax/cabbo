from enum import Enum

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime
from models.common import S3ObjectInfo
from models.user.user_enum import GenderEnum


class CustomerPayment(BaseModel):
    id: Optional[str] = None  # Customer ID, if available
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    contact: Optional[str] = None  # Contact number, can be phone or email

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
    

class CustomerOnboardInitiationRequest(BaseModel):
    phone_number: str


class CustomerLoginRequest(BaseModel):
    phone_number: str
    otp: str


class CustomerLoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    customer_id: str
    first_time_login: Optional[bool] = None


class CustomerSuspensionRequest(BaseModel):
    customer_id: Optional[str] = None
    reason: Optional[str] = None
