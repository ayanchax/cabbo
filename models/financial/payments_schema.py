from typing import Optional
from pydantic import BaseModel

from models.customer.customer_schema import CustomerPayment

class PaymentOrderSchema(BaseModel):
    id: Optional[str] = None  # Order ID from vendor (e.g., Razorpay)

class PaymentNotesSchema(BaseModel):
    reference_source_id: Optional[str] = None  # Reference ID for the order, if applicable
    trip_type_id: Optional[str] =None # e.g., "local", "outstation", "airport"
    requestor: Optional[str]=None  # e.g., "customer", "driver"
    passenger_id: Optional[str] = None  # Optional passenger ID for trip-related payments
    additional_info: Optional[dict] = None  # Any additional information that might be needed
    metadata: Optional[dict] = None  # Additional metadata if required
    message: Optional[str] = None  # Optional message for the payment order
    customer:Optional[CustomerPayment] = None 

    class Config:
        from_attributes = True
        extra = "allow"  # Allow additional fields not defined in the schema
        exclude_none = True  # Exclude fields with None values from the model dump

class RazorpayOrderSchema(PaymentOrderSchema):
    reference_id: Optional[str] = None  # Reference ID for the order, if applicable
    description: Optional[str] = None  # Description of the order
    customer:Optional[CustomerPayment] = None  # Customer details for the order
    callback_url: Optional[str] = None  # URL to call back after payment completion
    callback_method: Optional[str] = "get"  # HTTP method for the callback (GET/POST)
    reminder_enable: Optional[bool] = False  # Whether to enable payment reminders
    accept_partial: Optional[bool] = True  # Whether to accept partial payments
    notify:Optional[dict[str, bool]] = None  # Notification settings for the order
    amount: float  # Amount in the smallest currency unit (e.g., paise for INR)
    currency: str  # Currency code (e.g., "INR")
    receipt: Optional[str] = None  # Receipt identifier
    notes: Optional[PaymentNotesSchema] = None  # Additional notes for the order

    class Config:
        from_attributes = True
        extra = "allow"  # Allow additional fields not defined in the schema

class RazorPayPaymentResponse(BaseModel):
    razorpay_order_id: str  # Razorpay order ID
    razorpay_payment_id: str  # Razorpay payment ID
    razorpay_signature: Optional[str]  # Razorpay payment signature
    
    class Config:
        from_attributes = True
        extra = "allow"  # Allow additional fields not defined in the schema

class BankDetailsSchema(BaseModel):
    account_holder_name: str  # Name of the bank account holder
    account_number: str  # Bank account number
    ifsc_code: str  # IFSC code for the bank branch
    bank_name: Optional[str] = None  # Name of the bank (optional)
    branch_name: Optional[str] = None  # Name of the bank branch (optional)

    class Config:
        from_attributes = True
        extra = "allow"  # Allow additional fields not defined in the schema
        exclude_none = True  # Exclude fields with None values from the model dump