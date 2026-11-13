from core import refund_error_codes as refund_errors
from models.financial.payments_enum import ReconciliationStateEnum
from typing import Optional

from core.exceptions import UNSUPPORTED_PAYMENT_PROVIDER, CabboException
from models.customer.customer_orm import Customer
from models.financial.payments_schema import PaymentNotesSchema
from models.financial.payments_schema import RazorPayPaymentResponse
from models.financial.payments_schema import ReconciliationOutcome
from models.policies.refund_enum import PaymentProvider
from models.pricing.pricing_schema import Currency
from core.config import settings
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_schema import TripBookRequest
from services.razorpay_service import (
    parse_razorpay_webhook,
    fetch_razorpay_order_payment,
    get_initialization_refund_response,
    get_razorpay_payment_order,
    verify_razorpay_payment,
)
from sqlalchemy.ext.asyncio import AsyncSession
from services.razorpay_refund_service import (
    RefundReviewRequired, RefundRetryableError,
    reconcile_or_submit_refund as reconcile_or_submit_razorpay_refund,
    fetch_refund as fetch_razorpay_refund,
)


PAYMENT_PROVIDER = settings.PAYMENT_PROVIDER


def reconcile_or_submit_refund(*, payment_id, amount, original_amount, currency,
                             order_id, idempotency_key, entity_id, provider=PAYMENT_PROVIDER):
    """Dispatch durable refund submission; amounts are in provider subunits."""
    if provider == PaymentProvider.razorpay.value:
        return reconcile_or_submit_razorpay_refund(
            payment_id=payment_id, amount=amount, original_amount=original_amount,
            currency=currency, order_id=order_id, idempotency_key=idempotency_key,
            entity_id=entity_id)
    # The worker preserves this obligation for review instead of retrying an
    # unsupported provider indefinitely or silently treating it as success.
    raise RefundReviewRequired(refund_errors.UNSUPPORTED_REFUND_PROVIDER)


def fetch_refund(*, refund_id, payment_id, amount, currency, provider=PAYMENT_PROVIDER):
    """Dispatch a validated refund lookup without hiding transient failures."""
    if provider == PaymentProvider.razorpay.value:
        return fetch_razorpay_refund(
            refund_id=refund_id, payment_id=payment_id, amount=amount, currency=currency)
    raise RefundReviewRequired(refund_errors.UNSUPPORTED_REFUND_PROVIDER)



async def receive_payment_webhook(provider: str, raw_body: bytes, signature: str, event_id: str, db:AsyncSession):
    """Authenticate and durably enqueue a provider event before HTTP acknowledgement."""
    import hashlib
    from fastapi import HTTPException
    from services.payment_webhook_service import a_store_payment_webhook
    if provider == PaymentProvider.razorpay.value:
        notice = parse_razorpay_webhook(raw_body, signature)
        if notice is None:
                return False
        await a_store_payment_webhook(notice, event_id, hashlib.sha256(raw_body).hexdigest(), db)
        return True
    raise HTTPException(status_code=503, detail="Payment webhook provider is not enabled")
    


def fetch_payment_order_status(order_id: str, expected_amount: int, expected_currency: str, provider= PAYMENT_PROVIDER) -> ReconciliationOutcome:
    """Route reconciliation reads and payment-response formatting to the provider."""
    if provider == PaymentProvider.razorpay.value:
        outcome = fetch_razorpay_order_payment(order_id, expected_amount, expected_currency)
        if outcome.state == ReconciliationStateEnum.captured:
            outcome.payment_info = RazorPayPaymentResponse(
                    razorpay_order_id=order_id,
                    razorpay_payment_id=outcome.payment_id,
                    razorpay_signature=None,
            )
        return outcome
    raise CabboException(
        "Payment reconciliation is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER,
    )


def get_booking_payment_order(
    booking_request: TripBookRequest,
    customer: Customer,
    temp_trip: TempTrip,
    currency: Currency,
    silently_fail: bool = False,
    existing_order_id: Optional[str] = None,
    provider= PAYMENT_PROVIDER
):
    if provider == PaymentProvider.razorpay.value:
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


def verify_payment(
    payment_details: dict,
    silently_fail: bool = False,
    expected_order_id: Optional[str] = None,
    expected_amount: Optional[int] = None,
    expected_currency: Optional[str] = None,
    provider= PAYMENT_PROVIDER
):
    if provider == PaymentProvider.razorpay.value:
        return verify_razorpay_payment(
            payment_detail=payment_details,
            expected_order_id=expected_order_id,
            expected_amount=expected_amount,
            expected_currency=expected_currency,
        )

    if silently_fail:
        return None
    raise CabboException(
        "Payment verification is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )


def get_initial_refund_response(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency: Currency,
    silently_fail: bool = False,
    provider= PAYMENT_PROVIDER
):
    if provider == PaymentProvider.razorpay.value:
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


def get_payment_id_prefix(provider= PAYMENT_PROVIDER):
    if provider == PaymentProvider.razorpay.value:
        return "pay_"
    raise CabboException(
        "Payment ID prefix retrieval is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )

def get_refund_id_prefix(provider= PAYMENT_PROVIDER):
    if provider == PaymentProvider.razorpay.value:
        return "rfnd_"
    raise CabboException(
        "Refund ID prefix retrieval is not supported for the configured payment provider",
        status_code=400,
        error_code=UNSUPPORTED_PAYMENT_PROVIDER
    )
