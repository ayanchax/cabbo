
from typing import Optional
from pydantic import BaseModel, EmailStr, Field, model_validator
from core.exceptions import CabboException
from models.common import AmenitiesSchema, S3ObjectInfo
from models.financial.payments_enum import PaymentModeEnum
from models.financial.payments_schema import BankDetailsSchema
from models.map.location_schema import Address
from models.pricing.pricing_schema import ExtraPayments
from models.trip.trip_enums import CarTypeEnum, FuelTypeEnum
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
    is_active: Optional[bool] = True  # Flag to indicate if the driver is currently active and available for trips, we can use this field to temporarily deactivate a driver without deleting their record from the database, for example, if they are on a break, on vacation, or if they have been suspended for any reason, we can set is_active to false and they will not be assigned any new trips until they are reactivated by setting is_active back to true. This way we can maintain the driver's historical data and trip records while also managing their availability for new trips effectively.
    s3_image_info: Optional[S3ObjectInfo] = None  # Stores S3 key and URL for the driver's profile picture if using S3 for storage.
    
    class Config:
        extra="allow"
        from_attributes = True
        exclude_none = True  # Exclude fields with None values from the model dump

class DriverCreateSchema(DriverBaseSchema):
    cab_type: CarTypeEnum  # Type of car (e.g., sedan, SUV)
    fuel_type: FuelTypeEnum  # Fuel type of the car (e.g., petrol, diesel, electric, hybrid)
    cab_model_and_make: str  # Model of the car (e.g., Maruti Swift)
    cab_registration_number: str  # Registration number of the car
    cab_amenities:Optional[AmenitiesSchema]=None # Cab amenities details
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
    cab_amenities:Optional[AmenitiesSchema]=None # Cab amenities details
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



class DriverReadSchema(DriverCreateSchema):
    pass


class DriverEarningSchema(BaseModel):
    trip_id: str=Field(..., description="Unique identifier for the trip")
    driver_id: str=Field(..., description="Unique identifier for the driver")
    earnings: float=Field(..., description="Base earnings for the trip which is the final price minus the platform fee, this is the amount that driver earns for the trip from Cabbo's end, excluding any extra earnings such as tolls paid by driver, parking charges paid by driver, overage payment for extra distance or time beyond what was estimated, tips given to driver by customer for good performance, high ratings, or completing a certain number of trips, etc.")
    extra_earnings: Optional[float] = Field(0.0, description="Any extra earnings for the driver on top of the standard fare for the trip, such as tolls paid by driver, parking charges paid by driver, overage payment for extra distance or time beyond what was estimated, tips given to driver by customer for good performance, high ratings, or completing a certain number of trips, etc.")
    extra_earnings_breakdown: Optional[ExtraPayments] = Field(None, description="Breakdown of any extra earnings for the driver on top of the standard fare for the trip in a structured format e.g., {'toll_charges': 100, 'parking_charges': 50, 'overage_payment': 30, 'tip': 1.5}")
    total_earnings: float=Field(..., description="Total earnings for the driver for the trip including the standard fare and any extra earnings (earnings + extra_earnings)")

    class Config:
        from_attributes = True
        extra="allow"

