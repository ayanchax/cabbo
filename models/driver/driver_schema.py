
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator, model_validator
from core.exceptions import CabboException
from models.financial.payments_enum import PaymentModeEnum
from models.financial.payments_schema import BankDetailsSchema
from models.trip.trip_enums import CarTypeEnum
from models.user.user_enum import GenderEnum, NationalityEnum, ReligionEnum
from utils.utility import validate_and_sanitize_country_phone
from datetime import datetime

 

class DriverBaseSchema(BaseModel):
    id: Optional[str] = None  # Unique identifier for the driver
    name: str  # Driver's name
    email: Optional[EmailStr] = None  # Driver's email address
    phone: str  # Driver's phone number
    dob: Optional[datetime] = None  # Date of birth
    gender: Optional[GenderEnum] = None  # Driver's gender
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None
    nationality: Optional[NationalityEnum] = NationalityEnum.indian  # e.g., Indian, American
    religion: Optional[ReligionEnum] = None  # e.g., Hindu, Muslim, Christian

    @field_validator("phone", "emergency_contact_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)
    
    class Config:
        from_attributes = True
        exclude_none = True  # Exclude fields with None values from the model dump

class DriverCreateSchema(DriverBaseSchema):
    car_type: CarTypeEnum  # Type of car (e.g., sedan, SUV)
    car_model: str  # Model of the car (e.g., Maruti Swift)
    car_registration_number: str  # Registration number of the car
    payment_mode: PaymentModeEnum  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str]  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments

    #Validate if payment_mode is gpay phonepe or paytm then payment_phone_number is required, and if it is bank_transfer then bank_details is required
    
    
    @model_validator(mode="after")
    def payment_mode_validator(self):
        payment_mode = self.payment_mode
        payment_phone_number = self.payment_phone_number
        bank_details = self.bank_details
        if payment_mode in [PaymentModeEnum.gpay, PaymentModeEnum.phonepe, PaymentModeEnum.paytm] and not payment_phone_number:
            raise CabboException("payment_phone_number is required for UPI payments.", status_code=422)

        
        if payment_mode == PaymentModeEnum.bank_transfer and not bank_details:
            raise CabboException("bank_details is required for bank transfer payments.", status_code=422)

        return self

    @field_validator("payment_phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)
    
    class Config:
        from_attributes = True
        exclude_none = True  # Exclude fields with None values from the model dump


class DriverUpdateSchema(DriverBaseSchema):
    car_type: Optional[CarTypeEnum] = None  # Type of car (e.g., sedan, SUV)
    car_model: Optional[str] = None  # Model of the car (e.g., Maruti Swift)
    car_registration_number: Optional[str] = None  # Registration number of the car
    payment_mode: Optional[PaymentModeEnum] = None  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str] = None  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments

    @model_validator(mode="after")
    def payment_mode_validator(self):
        payment_mode = self.payment_mode
        payment_phone_number = self.payment_phone_number
        bank_details = self.bank_details
        if payment_mode in [PaymentModeEnum.gpay, PaymentModeEnum.phonepe, PaymentModeEnum.paytm] and not payment_phone_number:
            raise CabboException("payment_phone_number is required for UPI payments.", status_code=422)

        
        if payment_mode == PaymentModeEnum.bank_transfer and not bank_details:
            raise CabboException("bank_details is required for bank transfer payments.", status_code=422)

        return self

    @field_validator("payment_phone_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)

    # All fields are optional for update
    class Config:
        from_attributes = True
        extra="forbid"
        exclude_none = True  # Exclude fields with None values from the model dump


