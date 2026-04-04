from core.exceptions import CabboException
from models.customer.customer_orm import Customer
from models.financial.payments_schema import PaymentNotesSchema
from models.policies.refund_enum import PaymentProvider
from models.pricing.pricing_schema import Currency
from core.config import settings
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_schema import TripBookRequest
from services.razorpay_service import (
    get_razorpay_payment_order,
    get_razorpay_refund_status,
    initiate_razorpay_refund,
    verify_razorpay_payment,
)

PAYMENT_PROVIDER = settings.PAYMENT_PROVIDER


def get_booking_payment_order(
    booking_request: TripBookRequest,
    customer: Customer,
    temp_trip: TempTrip,
    currency: Currency,
    silently_fail: bool = False,
):
    if PAYMENT_PROVIDER == PaymentProvider.razorpay.value:
        return get_razorpay_payment_order(
            booking_request, customer, temp_trip, currency
        )
    if silently_fail:
        return None
    raise CabboException(
        "Payment processing is not supported for the configured payment provider",
        status_code=400,
    )


def verify_payment(payment_details: dict, silently_fail: bool = False):
    if PAYMENT_PROVIDER == PaymentProvider.razorpay.value:
        return verify_razorpay_payment(payment_details)

    if silently_fail:
        return None
    raise CabboException(
        "Payment verification is not supported for the configured payment provider",
        status_code=400,
    )


def initiate_refund(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency: Currency,
    silently_fail: bool = False,
):
    if PAYMENT_PROVIDER == PaymentProvider.razorpay.value:
        return initiate_razorpay_refund(payment_id, refund_amount, notes, currency)
    if silently_fail:
        return None
    raise CabboException(
        "Refunds are not supported for the configured payment provider", status_code=400
    )


def get_refund_status(refund_id: str, silently_fail: bool = False):
    if PAYMENT_PROVIDER == PaymentProvider.razorpay.value:
        return get_razorpay_refund_status(refund_id)

    if silently_fail:
        return None
    raise CabboException(
        "Refund status retrieval is not supported for the configured payment provider",
        status_code=400,
    )
