"""Synchronous provider operations; callers run these outside the asyncio loop."""
from core import refund_error_codes as refund_errors


from models.financial.payments_enum import ReconciliationStateEnum
from models.policies.refund_enum import RefundStatus
from services.razorpay_service import create_razorpay_refund_client


class RefundReviewRequired(Exception):
    """Cannot safely move money automatically; keep the obligation for review."""


class RefundRetryableError(Exception):
    """Provider state is unavailable or not ready; preserve intent and retry."""

REFUND_TIMEOUT = 20
REFUND_HISTORY_PAGE_SIZE = 100
# Bound provider work; reaching this limit requires review instead of assuming
# that an incomplete refund history permits another payout.
REFUND_HISTORY_MAX_PAGES = 100
MINIMUM_INR_REFUND_SUBUNITS = 100  # INR 1.00 in paise.
EXPECTED_REFUNDS_PER_PAYMENT = 1

EXPECTED_EXCEPTION_KEYWORDS=("not supported", "disabled", "dispute", "cannot be created",
                "different request with the same", "fully refunded")

def validate_refund(refund, payment_id, amount, currency):
    if (not str(refund.get("id", "")).startswith("rfnd_")
            or refund.get("payment_id") != payment_id
            or refund.get("amount") != amount or refund.get("currency") != currency):
        raise RefundReviewRequired(refund_errors.PROVIDER_REFUND_MISMATCH)
    if refund.get("status") not in (RefundStatus.pending.value, RefundStatus.processed.value, RefundStatus.failed.value):
        raise RefundRetryableError(refund_errors.UNKNOWN_PROVIDER_REFUND_STATUS)
    return refund


def reconcile_or_submit_refund( payment_id, amount, original_amount,
                               currency, order_id, idempotency_key, entity_id):
    """Recover manual/uncertain refunds before submitting the same durable intent."""
    if not payment_id or not payment_id.startswith("pay_"):
        raise RefundReviewRequired(refund_errors.MISSING_PAYMENT_ID)
    if (amount <= 0 or amount > original_amount
            or (currency == "INR" and amount < MINIMUM_INR_REFUND_SUBUNITS)):
        raise RefundReviewRequired(refund_errors.INVALID_REFUND_AMOUNT)
    client = create_razorpay_refund_client()
    payment = client.payment.fetch(payment_id, timeout=REFUND_TIMEOUT)
    if (payment.get("id") != payment_id or payment.get("currency") != currency
            or payment.get("amount") != original_amount
            or not order_id or payment.get("order_id") != order_id):
        raise RefundReviewRequired(refund_errors.PAYMENT_IDENTITY_OR_AMOUNT_MISMATCH)

    # Inspect every page, not just the first refund. A manual Dashboard refund
    # must be adopted only when its identity and amount satisfy this obligation.
    refunds = []
    for page in range(REFUND_HISTORY_MAX_PAGES):
        items = client.payment.fetch_multiple_refund(
            payment_id, {"count": REFUND_HISTORY_PAGE_SIZE,
                         "skip": page * REFUND_HISTORY_PAGE_SIZE}, timeout=REFUND_TIMEOUT)["items"]
        refunds.extend(items)
        if len(items) < REFUND_HISTORY_PAGE_SIZE:
            # No more pages; the provider has returned all refunds for this payment.
            break
    else:
        raise RefundReviewRequired(refund_errors.REFUND_HISTORY_TOO_LARGE)
    if refunds:
        if len(refunds) != EXPECTED_REFUNDS_PER_PAYMENT:
            raise RefundReviewRequired(refund_errors.MULTIPLE_PROVIDER_REFUNDS)
        return validate_refund(refunds[0], payment_id, amount, currency)

    if payment.get("status") != ReconciliationStateEnum.captured.value:
        if payment.get("status") in (ReconciliationStateEnum.created.value, ReconciliationStateEnum.authorized.value):
            raise RefundRetryableError(refund_errors.PAYMENT_NOT_CAPTURED_YET)
        raise RefundReviewRequired(refund_errors.PAYMENT_NOT_REFUNDABLE)
    if payment.get("amount_refunded", 0) != 0:
        raise RefundReviewRequired(refund_errors.UNMATCHED_REFUNDED_AMOUNT)

    # No bank-settlement gate: Razorpay decides whether merchant balance is
    # sufficient. Keep the body/key stable across retries after an unknown result.
    try:
        refund = client.payment.refund(payment_id, {
            "amount": amount, "speed": "normal", "receipt": idempotency_key,
            "notes": {"reference_source_id": entity_id, "refund_intent": idempotency_key},
        }, headers={"X-Refund-Idempotency": idempotency_key}, timeout=REFUND_TIMEOUT)
    except Exception as exc:
        description = str(exc).lower()
        if "balance" in description or "insufficient" in description:
            raise RefundRetryableError(refund_errors.INSUFFICIENT_PROVIDER_BALANCE) from exc
        if any(text in description for text in EXPECTED_EXCEPTION_KEYWORDS):
            raise RefundReviewRequired(refund_errors.PROVIDER_SUBMISSION_REQUIRES_REVIEW) from exc
        # A timeout is not proof of failure. The next run lists refunds first
        # and uses the same idempotency key if submission must be retried.
        raise RefundRetryableError(refund_errors.PROVIDER_SUBMISSION_UNAVAILABLE) from exc
    return validate_refund(refund, payment_id, amount, currency)


def fetch_refund(refund_id, payment_id, amount, currency):
    client = create_razorpay_refund_client()
    return validate_refund(client.refund.fetch(refund_id, timeout=REFUND_TIMEOUT),
                           payment_id, amount, currency)
