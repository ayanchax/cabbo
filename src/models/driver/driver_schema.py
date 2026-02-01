
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, model_validator
from core.exceptions import CabboException
from models.financial.payments_enum import PaymentModeEnum
from models.financial.payments_schema import BankDetailsSchema
from models.map.location_schema import Address
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum
from models.trip.trip_schema import AmenitiesSchema
from models.user.user_enum import GenderEnum, NationalityEnum, ReligionEnum
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
    address:Optional[Address]=None

    
    class Config:
        from_attributes = True
        exclude_none = True  # Exclude fields with None values from the model dump

class DriverCreateSchema(DriverBaseSchema):
    cab_type: CarTypeEnum  # Type of car (e.g., sedan, SUV)
    fuel_type: FuelTypeEnum  # Fuel type of the car (e.g., petrol, diesel, electric, hybrid)
    cab_model_and_make: str  # Model of the car (e.g., Maruti Swift)
    cab_registration_number: str  # Registration number of the car
    amenities:Optional[AmenitiesSchema]=None # Cab amenities details
    payment_mode: PaymentModeEnum  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str]  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments

    #Validate if payment_mode is gpay phonepe or paytm then payment_phone_number is required, and if it is bank_transfer then bank_details is required
    
    
    @model_validator(mode="after")
    def payment_mode_validator(self):
        payment_mode = self.payment_mode
        if not self.payment_phone_number or self.payment_phone_number.strip() == "":
            self.payment_phone_number=self.phone # Use driver's primary phone number if alternate not provided
        payment_phone_number = self.payment_phone_number
        bank_details = self.bank_details
        if payment_mode in [PaymentModeEnum.gpay, PaymentModeEnum.phonepe, PaymentModeEnum.paytm] and not payment_phone_number:
            raise CabboException("payment_phone_number is required for UPI payments.", status_code=422)

        
        if payment_mode == PaymentModeEnum.bank_transfer and not bank_details:
            raise CabboException("bank_details is required for bank transfer payments.", status_code=422)

        return self

    
    class Config:
        from_attributes = True
        exclude_none = True  # Exclude fields with None values from the model dump


class DriverUpdateSchema(DriverBaseSchema):
    cab_type: Optional[CarTypeEnum] = None  # Type of car (e.g., sedan, SUV)
    fuel_type: Optional[FuelTypeEnum] = None  # Fuel type of the car (e.g., petrol, diesel, electric, hybrid)
    cab_model_and_make: Optional[str] = None  # Model of the car (e.g., Maruti Swift)
    cab_registration_number: Optional[str] = None  # Registration number of the car
    amenities:Optional[AmenitiesSchema]=None # Cab amenities details
    payment_mode: Optional[PaymentModeEnum] = None  # Payment mode (e.g., gpay, phonepe, paytm)
    payment_phone_number: Optional[str] = None  # Alternate payment phone number for UPI payments
    bank_details: Optional[BankDetailsSchema] = None  # Bank details for bank transfer payments
    
    @model_validator(mode="after")
    def payment_mode_validator(self):
        payment_mode = self.payment_mode
        if not self.payment_phone_number or self.payment_phone_number.strip() == "":
            self.payment_phone_number=self.phone # Use driver's primary phone number if alternate not provided
        payment_phone_number = self.payment_phone_number
        bank_details = self.bank_details
        if payment_mode in [PaymentModeEnum.gpay, PaymentModeEnum.phonepe, PaymentModeEnum.paytm] and not payment_phone_number:
            raise CabboException("payment_phone_number is required for UPI payments.", status_code=422)

        
        if payment_mode == PaymentModeEnum.bank_transfer and not bank_details:
            raise CabboException("bank_details is required for bank transfer payments.", status_code=422)

        return self

    

    # All fields are optional for update
    class Config:
        from_attributes = True
        extra="forbid"
        exclude_none = True  # Exclude fields with None values from the model dump


class DriverReadProfilePictureAfterUpdate(BaseModel):
    image_url: str = Field(None, description="URL to the driver's profile picture")
    last_modified: datetime = Field(
        None, description="Last modified date of the driver's profile"
    )

class DriverReadSchema(DriverCreateSchema):
    pass

