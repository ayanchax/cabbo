import enum


class ReconciliationStateEnum(str, enum.Enum):
    checking = "checking"
    captured = "captured"
    booked = "booked"
    review_required = "review_required"


class PaymentModeEnum(str, enum.Enum):
     gpay = "gpay"
     phonepe = "phonepe"
     paytm = "paytm"
     bank_transfer = "bank_transfer"
