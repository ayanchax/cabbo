
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from models.financial.payments_enum import PaymentModeEnum
from models.financial.payments_schema import BankDetailsSchema
from models.trip.trip_enums import CarTypeEnum
from models.user.user_enum import GenderEnum, NationalityEnum, ReligionEnum
from utils.utility import validate_and_sanitize_country_phone
from datetime import datetime

class DriverBaseSchema(BaseModel):
    id: str  # Unique identifier for the driver

class DriverCreateSchema(DriverBaseSchema):
    name: str  # Driver's name
    email: Optional[EmailStr]=None  # Driver's email address
    phone_number: str  # Driver's phone number
    dob: Optional[datetime] = None
    gender:Optional[GenderEnum]=GenderEnum.male  # Driver gender, defaults to Male
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    nationality: Optional[NationalityEnum] = NationalityEnum.indian  # e.g., Indian, American
    religion: Optional[ReligionEnum] = None  # e.g., Hindu, Muslim, Christian
    car_type: CarTypeEnum  # Type of car (e.g., sedan, SUV)
    car_model: str  # Model of the car (e.g., Maruti Swift)
    car_registration_number: str  # Registration number of the car
    payment_mode: PaymentModeEnum  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str]  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments

    @field_validator("phone_number", "payment_phone_number" "emergency_contact_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)
    
    class Config:
        exclude_none = True  # Exclude fields with None values from the model dump


class DriverUpdateSchema(DriverBaseSchema):
    name: Optional[str] = None  # Driver's name
    email: Optional[EmailStr] = None  # Driver's email address
    phone_number: Optional[str] = None  # Driver's phone number
    gender: Optional[GenderEnum] = None  # Driver gender
    dob: Optional[datetime] = None  # Date of birth
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    nationality: Optional[NationalityEnum] = None  # e.g., Indian, American
    religion: Optional[ReligionEnum] = None  # e.g., Hindu, Muslim,
    car_type: Optional[CarTypeEnum] = None  # Type of car (e.g., sedan, SUV)
    car_model: Optional[str] = None  # Model of the car (e.g., Maruti Swift)
    car_registration_number: Optional[str] = None  # Registration number of the car
    payment_mode: Optional[PaymentModeEnum] = None  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str] = None  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments

    @field_validator("phone_number", "payment_phone_number", "emergency_contact_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)

    class Config:
        exclude_none = True  # Exclude fields with None values from the model dump

