from enum import Enum

class RefundType(str, Enum):
    full = "full"
    partial = "partial"
    other = "other"

class RefundStatus(str, Enum):
    processed="processed"
    pending = "pending"
    completed = "completed"
    failed = "failed"
    unknown = "unknown"

class RefundTrigger(str, Enum):
    manual = "manual"
    automatic = "automatic"

class PaymentProvider(str, Enum):
    razorpay = "razorpay"
    stripe= "stripe"
    phonepe = "phonepe"