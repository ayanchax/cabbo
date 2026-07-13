import enum


class PaymentModeEnum(str, enum.Enum):
     gpay = "gpay"
     phonepe = "phonepe"
     paytm = "paytm"
     bank_transfer = "bank_transfer"
