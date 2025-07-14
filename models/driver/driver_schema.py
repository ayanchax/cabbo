
from typing import List, Optional
from pydantic import BaseModel, EmailStr, field_validator
from models.documents.kyc_document_enum import KYCDocumentTypeEnum
from models.financial.payments_enum import PaymentModeEnum
from models.financial.payments_schema import BankDetailsSchema
from utils.utility import validate_and_sanitize_country_phone


class DriverBaseSchema(BaseModel):
    id: str  # Unique identifier for the driver

class DriverCreateSchema(DriverBaseSchema):
    name: str  # Driver's name
    email: Optional[EmailStr]=None  # Driver's email address
    phone_number: str  # Driver's phone number
    car_type: str  # Type of car (e.g., sedan, SUV)
    car_model: str  # Model of the car (e.g., Maruti Swift)
    car_registration_number: str  # Registration number of the car
    payment_mode: PaymentModeEnum  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str]  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments

    @field_validator("phone_number", "payment_phone_number", mode="before")
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
    car_type: Optional[str] = None  # Type of car (e.g., sedan, SUV)
    car_model: Optional[str] = None  # Model of the car (e.g., Maruti Swift)
    car_registration_number: Optional[str] = None  # Registration number of the car
    payment_mode: Optional[PaymentModeEnum] = None  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str] = None  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments

    @field_validator("phone_number", "payment_phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)

    class Config:
        exclude_none = True  # Exclude fields with None values from the model dump

