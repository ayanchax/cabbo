from typing import Optional

from cabbo_core.exceptions import UNSUPPORTED_PAYMENT_PROVIDER, CabboException
from cabbo_core.models.customer.customer_orm import Customer
from cabbo_core.models.financial.payments_schema import PaymentNotesSchema
from cabbo_core.models.policies.refund_enum import PaymentProvider
from cabbo_core.models.pricing.pricing_schema import Currency
from cabbo_core.models.trip.temp_trip_orm import TempTrip
from cabbo_core.models.trip.trip_schema import TripBookRequest
from cabbo_core.services.razorpay_service import (
    get_initialization_refund_response,
    get_razorpay_payment_order,
    get_razorpay_refund_status,
    initiate_razorpay_refund,
    is_eligible_razorpay_identifier,
    is_eligible_to_attempt_razor_pay_refund_initiation,
    is_razorpay_payment_settled,
    verify_razorpay_payment,
)



def get_booking_payment_order(
    booking_request: TripBookRequest,
    customer: Customer,
    temp_trip: TempTrip,
    currency: Currency,
    silently_fail: bool = False,
    existing_order_id: Optional[str] = None,
    provider=PaymentProvider.razorpay
):
    if provider == PaymentProvider.razorpay:
        return get_razorpay_payment_order(
            booking_request, customer, temp_trip, currency, existing_order_id=existing_order_id
        )
    if silently_fail:
        return None
    raise CabboException(
        "Payment processing is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )


def verify_payment(payment_details: dict, silently_fail: bool = False,provider=PaymentProvider.razorpay):
    if provider == PaymentProvider.razorpay:
        return verify_razorpay_payment(payment_details)

    if silently_fail:
        return None
    raise CabboException(
        "Payment verification is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )


def initiate_refund(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency: Currency,
    silently_fail: bool = False,
    provider=PaymentProvider.razorpay
):
    if provider == PaymentProvider.razorpay:
        return initiate_razorpay_refund(payment_id, refund_amount, notes, currency)
    if silently_fail:
        return None
    raise CabboException(
        "Refunds are not supported for the configured payment provider", status_code=400, error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )


def get_refund_status(refund_id: str, silently_fail: bool = False,provider=PaymentProvider.razorpay):
    if provider == PaymentProvider.razorpay:
        return get_razorpay_refund_status(refund_id)

    if silently_fail:
        return None
    raise CabboException(
        "Refund status retrieval is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )


def is_payment_settled(payment_id: str, silently_fail: bool = False, provider=PaymentProvider.razorpay):
    if provider == PaymentProvider.razorpay:
        return is_razorpay_payment_settled(payment_id)

    if silently_fail:
        return None
    raise CabboException(
        "Payment settlement status retrieval is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )


def get_initial_refund_response(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency: Currency,
    silently_fail: bool = False,
    provider=PaymentProvider.razorpay
):
    if provider == PaymentProvider.razorpay:
        return get_initialization_refund_response(
            payment_id, refund_amount, notes, currency
        )
    if silently_fail:
        return None
    raise CabboException(
        "Refund initialization is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )


def is_eligible_payment_identifier(id:str, provider=PaymentProvider.razorpay):
    if provider == PaymentProvider.razorpay:
        return is_eligible_razorpay_identifier(id)
    # Add conditions for other payment providers as needed
    return False

def is_eligible_to_attempt_refund_initiation(payment_id:str, provider=PaymentProvider.razorpay):
    if provider == PaymentProvider.razorpay:
        return is_eligible_to_attempt_razor_pay_refund_initiation(payment_id, silently_fail=True) or (payment_id and payment_id.startswith("pay_"))
    return False