from core.exceptions import CabboException
from models.customer.customer_orm import Customer
from models.financial.payments_schema import PaymentNotesSchema
from models.pricing.pricing_schema import Currency
from core.config import settings
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_schema import TripBookRequest
from services.razorpay_service import (
    get_razorpay_payment_order,
    initiate_razorpay_refund,
    verify_razorpay_payment,
)

PAYMENT_PROVIDER = settings.PAYMENT_PROVIDER


def get_booking_payment_order(
    booking_request: TripBookRequest,
    customer: Customer,
    temp_trip: TempTrip,
    currency: Currency,
):
    if PAYMENT_PROVIDER == "razorpay":
        return get_razorpay_payment_order(
            booking_request, customer, temp_trip, currency
        )
    raise CabboException(
        "Payment processing is not supported for the configured payment provider",
        status_code=400,
    )


def verify_payment(payment_details: dict):
    if PAYMENT_PROVIDER == "razorpay":
        return verify_razorpay_payment(payment_details)
    raise CabboException(
        "Payment verification is not supported for the configured payment provider",
        status_code=400,
    )


def initiate_refund(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency: Currency,
):
    if PAYMENT_PROVIDER == "razorpay":
        return initiate_razorpay_refund(payment_id, refund_amount, notes, currency)
    raise CabboException(
        "Refunds are not supported for the configured payment provider", status_code=400
    )
