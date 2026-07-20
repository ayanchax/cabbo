import sys
from pathlib import Path
from typing import Optional

parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from models.policies.refund_enum import RefundType

from enum import Enum
import logging

import razorpay.errors
from core.constants import APP_NAME, APP_VERSION
from core.exceptions import RAZORPAY_PAYMENT_ORDER_CREATION_FAILED, CabboException
from models.customer.customer_orm import Customer
from models.customer.customer_schema import CustomerPayment
from models.financial.payments_schema import (
    PaymentNotesSchema,
    RazorPayPaymentResponse,
    RazorpayOrderSchema,
)
from sqlalchemy.orm import Session
import razorpay
from core.config import settings
from models.pricing.pricing_schema import Currency
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_schema import TripBookRequest
from utils.redaction import summarize_provider_entity
from utils.utility import convert_based_on_currency

log = logging.getLogger(__name__)

RAZOR_PAY_CLIENT = razorpay.Client(
    auth=(settings.RAZOR_PAY_KEY_ID, settings.RAZOR_PAY_KEY_SECRET)
)
RAZOR_PAY_CLIENT_DETAILS = {
    "version": APP_VERSION,
    "name": f"{APP_NAME.capitalize()} Trip Booking Service",
    "description": "Service for booking trips and managing payments.",
}


class RazorPayRefundStatusEnum(str, Enum):
    INITIATED = "initiated"  # Refund has been initiated and is in the system, but not yet processed by Razorpay
    PENDING = "pending"  # Refund queued but not yet processed
    PROCESSED = "processed"  # Refund has been processed by Razorpay and is in the system, but not yet reflected in customer's account
    FAILED = "failed"  # Refund processing failed due to some error, refund has not been processed by Razorpay and is not in the system


class RazorPayOrderStatusEnum(str, Enum):
    CREATED = "created"  # Order has been created but payment not yet attempted
    ATTEMPTED = "attempted"  # Payment has been attempted but not yet successful (e.g. customer abandoned payment or payment failed)
    PAID = "paid"  # Payment has been successful but not yet captured (e.g. authorized but not captured)


class RazorPayPaymentStatusEnum(str, Enum):
    CAPTURED = "captured"  # Payment has been successful and captured, this is the final successful state for a payment
    REFUNDED = "refunded"  # Payment has been refunded after being captured


def _format_razorpay_order(order: dict, conversion_factor: int) -> dict:
    """Format Razorpay order response."""
    return {
        **order,
        "amount": float(
            convert_based_on_currency(
                order.get("amount", 0), conversion_factor, convert_to_lowest=False
            )
        ),  # Convert paise to rupees as we want to work in standard currency units in UI
        "amount_in_lowest_unit": order.get(
            "amount", 0
        ),  # Also return amount in lowest unit (paise) as some Razorpay APIs require amount in paise for refunds, this saves the need for reconversion
        "amount_due": float(
            convert_based_on_currency(
                order.get("amount_due", 0), conversion_factor, convert_to_lowest=False
            )
        ),
    }

def _get_razorpay_existing_order(
    razorpay_order: RazorpayOrderSchema, order_id: Optional[str] = None
) -> dict:
    """Fetch an existing Razorpay order for the trip booking if it exists and is valid.
    Args:
        razorpay_order (RazorpayOrderSchema): The Razorpay order schema containing order details.
        order_id (Optional[str]): The existing Razorpay order ID, if available.
    Returns:
        dict: A dictionary containing the Razorpay order details if a valid existing order is found, None otherwise.
    """
    try:
        existing_order = RAZOR_PAY_CLIENT.order.fetch(order_id or razorpay_order.receipt)
        if existing_order and existing_order.get('status') == RazorPayOrderStatusEnum.CREATED.value:
            log.info(
                f"Found existing valid Razorpay order for receipt {razorpay_order.receipt}: "
                f"{summarize_provider_entity(existing_order)}"
            )
            _formatted_order =  _format_razorpay_order(existing_order, razorpay_order.currency_conversion_factor)
            _formatted_order["currency_symbol"] = razorpay_order.currency_symbol
            return _formatted_order

        else:
            log.info(f"No valid existing Razorpay order found for receipt {razorpay_order.receipt}")
            return None
    except razorpay.errors.BadRequestError as e:
        log.error(f"Error fetching existing Razorpay order for receipt {razorpay_order.receipt}: {str(e)}")
        return None
    except Exception as e:
        log.error(f"Unexpected error fetching existing Razorpay order for receipt {razorpay_order.receipt}: {str(e)}")
        return None


def _create_razorpay_order(
    razorpay_order: RazorpayOrderSchema, db: Session = None
) -> dict:
    """Create a Razorpay order for the trip booking.
    Args:
        razorpay_order (RazorpayOrderSchema): The Razorpay order schema containing order details.
        db (Session): The database session.
    Returns:
        dict: A dictionary containing the Razorpay order details.
    """
    try:
        client = RAZOR_PAY_CLIENT
        customer_notes = {
             
            "name": str(
                razorpay_order.notes.customer.name
                if razorpay_order.notes.customer
                else ""
            ),
            "contact": str(
                razorpay_order.notes.customer.contact
                if razorpay_order.notes.customer
                and razorpay_order.notes.customer.contact
                else ""
            ),
        }
        if razorpay_order.notes.customer and razorpay_order.notes.customer.email:
            customer_notes["email"] = str(razorpay_order.notes.customer.email)

        order_data = {
            "description": razorpay_order.description,
            "amount": int(
                convert_based_on_currency(
                    razorpay_order.amount, razorpay_order.currency_conversion_factor
                )
            ),  # Amount in paise as Razorpay expects amount in the smallest currency unit
            "currency": razorpay_order.currency,
            "receipt": razorpay_order.receipt,
            "notes": {
                "reference_source_id": str(
                    razorpay_order.notes.reference_source_id or ""
                ),
                "requestor": str(razorpay_order.notes.requestor or ""),
                "customer": customer_notes,
            },
        }
        client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
        order = client.order.create(data=order_data)
        if not order or "id" not in order:
            raise CabboException(
                "Failed to create Razorpay order.",
                status_code=500,
                error_code=RAZORPAY_PAYMENT_ORDER_CREATION_FAILED,
            )
        _formatted_order = _format_razorpay_order(
            order, razorpay_order.currency_conversion_factor
        )
        _formatted_order["currency_symbol"] = razorpay_order.currency_symbol
        log.info(
            f"Razorpay order created successfully: "
            f"{summarize_provider_entity(_formatted_order)}"
        )

        return _formatted_order
    except razorpay.errors.BadRequestError as e:
        log.error(f"Razorpay order creation failed: {str(e)}")
        raise CabboException(
            f"Razorpay order creation failed: {str(e)}",
            status_code=500,
            error_code=RAZORPAY_PAYMENT_ORDER_CREATION_FAILED,
        )
    except Exception as e:
        log.error(f"Unexpected error during Razorpay order creation: {str(e)}")
        raise CabboException(
            f"Unexpected error during Razorpay order creation: {str(e)}",
            status_code=500,
            error_code=RAZORPAY_PAYMENT_ORDER_CREATION_FAILED,
        )


def _populate_failed_razorpay_refund_response(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency_conversion_factor: int = 100,
    currency_code: str = "INR",
):
    refund_response = {
        "id": payment_id,  # Replace refund id with the payment id
        "status": RazorPayRefundStatusEnum.FAILED.value,
        "currency": currency_code,
        "notes": {
            "reference_source_id": str(notes.reference_source_id or ""),
            "refund_type": str(notes.refund_type or ""),
            "requestor": str(notes.requestor or ""),
            "customer_name": str(notes.customer.name if notes.customer else ""),
        },
        "payment_id": payment_id,
        "batch_id": None,
        "receipt": None,
        "entity": "refund",
        "amount": refund_amount,
        "base_amount": convert_based_on_currency(
            refund_amount, currency_conversion_factor
        ),
    }
    return refund_response


def _populate_initiated_razorpay_refund_response(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency_conversion_factor: int = 100,
    currency_code: str = "INR",
):
    refund_response = {
        "id": payment_id,  # Replace refund id with the payment id
        "status": RazorPayRefundStatusEnum.INITIATED.value,
        "currency": currency_code,
        "notes": {
            "reference_source_id": str(notes.reference_source_id or ""),
            "refund_type": str(notes.refund_type or ""),
            "requestor": str(notes.requestor or ""),
            "customer_name": str(notes.customer.name if notes.customer else ""),
        },
        "payment_id": payment_id,
        "batch_id": None,
        "receipt": None,
        "entity": "refund",
        "amount": refund_amount,
        "base_amount": convert_based_on_currency(
            refund_amount, currency_conversion_factor
        ),
    }
    return refund_response


def get_razorpay_payment_order(
    booking_request: TripBookRequest,
    customer: Customer,
    temp_trip: TempTrip,
    currency: Currency,
    existing_order_id: Optional[str] = None,
) -> tuple:

    razorpay_schema = RazorpayOrderSchema(
        description=f"Trip booking for {booking_request.preferences.trip_type} trip by {customer.name}",
        amount=temp_trip.platform_fee,  # Collect platform fee/convenience fee from the customer as part of the trip booking so that system is not abused
        currency=currency.code,
        currency_symbol=currency.symbol,
        currency_conversion_factor=currency.lowest_unit_conversion_factor,
        receipt=f"id#{temp_trip.id}",
        notes=PaymentNotesSchema(
            reference_source_id=temp_trip.id,
            customer=CustomerPayment(
                name=customer.name,
                email=customer.email or None,
                contact=customer.phone_number,
            ),
            requestor=temp_trip.creator_id,
        ),
    )
    trip_id = temp_trip.id  # Use the temporary trip ID as the booking ID
    if not existing_order_id:
        return trip_id, _create_razorpay_order(razorpay_order=razorpay_schema)
    else:
        return trip_id, _get_razorpay_existing_order(razorpay_order=razorpay_schema, order_id=existing_order_id)


def verify_razorpay_payment(
    payment_detail: dict,
    expected_order_id: Optional[str] = None,
    expected_amount: Optional[int] = None,
    expected_currency: Optional[str] = None,
):
    """
    Verify the payment status with Razorpay.
    This function should be called after the payment is completed to confirm the payment status.
    """
    client = RAZOR_PAY_CLIENT
    client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
    payment_id = None
    try:
        payment_detail: RazorPayPaymentResponse = RazorPayPaymentResponse.model_validate(
            payment_detail
        )
        payment_id = payment_detail.razorpay_payment_id
        order_id = expected_order_id or payment_detail.razorpay_order_id

        if not payment_detail.razorpay_signature:
            log.error("Payment verification failed: missing Razorpay signature.")
            return False

        if expected_order_id and payment_detail.razorpay_order_id != expected_order_id:
            log.error(
                f"Payment verification failed for {payment_id}: "
                f"order id mismatch. Expected {expected_order_id}, "
                f"got {payment_detail.razorpay_order_id}"
            )
            return False

        client.utility.verify_payment_signature(
            {
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": payment_detail.razorpay_signature,
            }
        )

        payment = client.payment.fetch(payment_id)
        if expected_order_id and payment.get("order_id") != expected_order_id:
            log.error(
                f"Payment verification failed for {payment_id}: "
                f"provider order id mismatch. Expected {expected_order_id}, "
                f"got {payment.get('order_id')}"
            )
            return False

        if expected_amount is not None and payment.get("amount") != expected_amount:
            log.error(
                f"Payment verification failed for {payment_id}: "
                f"amount mismatch. Expected {expected_amount}, got {payment.get('amount')}"
            )
            return False

        if expected_currency and payment.get("currency") != expected_currency:
            log.error(
                f"Payment verification failed for {payment_id}: "
                f"currency mismatch. Expected {expected_currency}, got {payment.get('currency')}"
            )
            return False

        if payment["status"] == RazorPayPaymentStatusEnum.CAPTURED.value:
            log.debug(
                f"Payment {payment_id} verified successfully."
            )
            return True
        else:
            log.error(
                f"Payment verification failed for {payment_id}: Status is {payment['status']}"
            )
            return False
    except razorpay.errors.BadRequestError as e:
        log.error(
            f"Payment verification failed for {payment_id}: {str(e)}"
        )
        return False  # If there's an error, we assume payment verification failed

    except Exception as e:
        log.error(
            f"Unexpected error during payment verification for {payment_id}: {str(e)}"
        )
        return False


def initiate_razorpay_refund(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency: Currency,
) -> dict:
    """
    Initiate a refund for a Razorpay payment.

    Args:
        payment_id (str): The Razorpay payment ID to refund.
        refund_amount (float): The amount to refund in rupees.
        trip_id (str): The ID of the trip associated with the refund.
        customer (CustomerRead): The customer details associated with the refund.
        currency (Currency): The currency used in the transaction.

    Returns:
        dict: A dictionary containing the refund details.
    """
    refund_data = {}
    try:
        client = RAZOR_PAY_CLIENT
        client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)

        refund_data = {
            "amount": int(
                convert_based_on_currency(
                    refund_amount, currency.lowest_unit_conversion_factor
                )
            ),  # Convert rupees to paise
        }

        if notes:
            refund_data["notes"] = {
                "reference_source_id": str(notes.reference_source_id or ""),
                "refund_type": str(notes.refund_type or ""),
                "requestor": str(notes.requestor or ""),
                "customer_name": str(notes.customer.name if notes.customer else ""),
            }

        # Guard: check if a refund already exists for this payment before initiating a new one
        # For Cabbo, a payment is always refunded once (full or partial) — this prevents duplicate refunds
        existing_refunds = client.payment.fetch_multiple_refund(payment_id)
        if existing_refunds and existing_refunds.get("items"):
            existing_refund = existing_refunds["items"][
                0
            ]  # Assuming only one refund per payment, take the first one
            log.info(
                f"Refund already exists for payment {payment_id} with status {existing_refund.get('status')}, returning existing refund instead of initiating new one"
            )

            return {
                **existing_refund,
                "amount": float(
                    convert_based_on_currency(
                        existing_refund.get("amount", 0),
                        currency.lowest_unit_conversion_factor,
                        convert_to_lowest=False,
                    )
                ),
            }

        refund = client.payment.refund(payment_id, refund_data)

        if not refund or "id" not in refund:
            return _populate_failed_razorpay_refund_response(
                payment_id=payment_id,
                refund_amount=refund_amount,
                notes=notes,
                currency_conversion_factor=currency.lowest_unit_conversion_factor,
                currency_code=currency.code,
            )

        # Format the refund response
        formatted_refund = {
            **refund,
            "amount": float(
                convert_based_on_currency(
                    refund.get("amount", 0),
                    currency.lowest_unit_conversion_factor,
                    convert_to_lowest=False,
                )
            ),  # Convert paise to rupees
        }

        log.info(
            f"Razorpay refund initiated successfully: "
            f"{summarize_provider_entity(formatted_refund)}"
        )
        return formatted_refund

    except razorpay.errors.BadRequestError as e:
        log.error(f"Razorpay refund creation failed: {str(e)}")

        return _populate_failed_razorpay_refund_response(
            payment_id=payment_id,
            refund_amount=refund_amount,
            notes=notes,
            currency_conversion_factor=currency.lowest_unit_conversion_factor,
            currency_code=currency.code,
        )

    except Exception as e:
        log.error(f"Unexpected error during Razorpay refund creation: {str(e)}")

        return _populate_failed_razorpay_refund_response(
            payment_id=payment_id,
            refund_amount=refund_amount,
            notes=notes,
            currency_conversion_factor=currency.lowest_unit_conversion_factor,
            currency_code=currency.code,
        )


def get_razorpay_refund_status(refund_id: str) -> RazorPayRefundStatusEnum:
    """
    Get the status of a Razorpay refund.

    Args:
        refund_id (str): The Razorpay refund ID.

    Returns:
        RazorPayRefundStatusEnum: The status of the refund.
    """
    # Razorpay refund IDs start with "rfnd_"; payment IDs start with "pay_".
    # A payment ID here means initiation failed — there is nothing to poll.

    if not refund_id or not refund_id.startswith("rfnd_"):
        log.warning(
            f"[razorpay_service] Skipping refund status check for {refund_id}: "
            f"no valid razorpay refund ID (got: {refund_id!r})"
        )
        return (
            RazorPayRefundStatusEnum.FAILED
        )  # Treat missing/invalid refund ID as failed status since there is nothing to poll

    client = RAZOR_PAY_CLIENT
    client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
    try:
        refund = client.refund.fetch(refund_id)
        status = refund.get("status")
        if status in RazorPayRefundStatusEnum._value2member_map_:
            return RazorPayRefundStatusEnum(status)
        else:
            log.error(f"Unknown refund status received from Razorpay: {status}")
            return RazorPayRefundStatusEnum.FAILED  # Treat unknown status as failed
    except razorpay.errors.BadRequestError as e:
        log.error(f"Failed to fetch Razorpay refund status for {refund_id}: {str(e)}")
        return RazorPayRefundStatusEnum.FAILED  # Treat errors as failed status
    except Exception as e:
        log.error(
            f"Unexpected error while fetching Razorpay refund status for {refund_id}: {str(e)}"
        )
        return (
            RazorPayRefundStatusEnum.FAILED
        )  # Treat unexpected errors as failed status


def is_razorpay_payment_settled(payment_id: str) -> bool:
    """
    Check if a Razorpay payment is settled (captured).
    Args:
        payment_id (str): The Razorpay payment ID to check.
    Returns:
        bool: True if the payment is settled, False otherwise.
    """
    client = RAZOR_PAY_CLIENT
    client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
    try:
        payment = client.payment.fetch(payment_id)
        log.info(
            f"Razorpay payment settlement check: "
            f"{summarize_provider_entity(payment)}"
        )
        settlement_id = payment.get("settlement_id", None)
        status = payment.get("status", None)
        refund_status = payment.get("refund_status", None)
        return (
            settlement_id is not None
            or status == RazorPayPaymentStatusEnum.REFUNDED.value
            or refund_status in (RefundType.full.value, RefundType.partial.value)
        )  # If settlement_id is present or payment is refunded, payment is settled
    except razorpay.errors.BadRequestError as e:
        log.error(f"Failed to fetch Razorpay payment status for {payment_id}: {str(e)}")
        return False  # Treat errors as not settled
    except Exception as e:
        log.error(
            f"Unexpected error while fetching Razorpay payment status for {payment_id}: {str(e)}"
        )
        return False  # Treat unexpected errors as not settled


def get_initialization_refund_response(
    payment_id: str,
    refund_amount: float,
    notes: PaymentNotesSchema,
    currency: Currency,
) -> dict:
    return _populate_initiated_razorpay_refund_response(
        payment_id=payment_id,
        refund_amount=refund_amount,
        notes=notes,
        currency_conversion_factor=currency.lowest_unit_conversion_factor,
        currency_code=currency.code,
    )


def is_eligible_razorpay_identifier(id: str):
    return id and (
        id.startswith("pay_") or id.startswith("rfnd_")
    )  # Razorpay payment IDs start with "pay_", refund IDs start with "rfnd_"


def is_eligible_to_attempt_razor_pay_refund_initiation(payment_id: str):
    return payment_id and payment_id.startswith("pay_")


if __name__ == "__main__":
    # Quick test to verify Razorpay integration is working
    test_payment_id = (
        "pay_SO51bSsBCz3BHV"  # Replace with a valid payment ID for testing
    )
    log.info(is_razorpay_payment_settled(test_payment_id))
