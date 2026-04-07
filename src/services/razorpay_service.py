import sys
from pathlib import Path

parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from enum import Enum
import logging

import razorpay.errors
from core.constants import APP_NAME, APP_VERSION
from core.exceptions import CabboException
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
from utils.utility import convert_based_on_currency

logger = logging.getLogger(__name__)

RAZOR_PAY_CLIENT = razorpay.Client(
    auth=(settings.RAZOR_PAY_KEY_ID, settings.RAZOR_PAY_KEY_SECRET)
)
RAZOR_PAY_CLIENT_DETAILS = {
    "version": APP_VERSION,
    "name": f"{APP_NAME.capitalize()} Trip Booking Service",
    "description": "Service for booking trips and managing payments.",
}


class RazorPayRefundStatusEnum(str, Enum):
    PENDING = "pending"  # Refund queued but not yet processed
    PROCESSED = "processed"  # Refund has been processed by Razorpay and is in the system, but not yet reflected in customer's account
    FAILED = "failed"  # Refund processing failed due to some error, refund has not been processed by Razorpay and is not in the system


class RazorPayOrderStatusEnum(str, Enum):
    CREATED = "created"  # Order has been created but payment not yet attempted
    ATTEMPTED = "attempted"  # Payment has been attempted but not yet successful (e.g. customer abandoned payment or payment failed)
    PAID = "paid"  # Payment has been successful but not yet captured (e.g. authorized but not captured)


class RazorPayPaymentStatusEnum(str, Enum):
    CAPTURED = "captured"  # Payment has been successful and captured, this is the final successful state for a payment


def _format_razorpay_order(order: dict, conversion_factor: int) -> dict:
    """Format Razorpay order response."""
    return {
        **order,
        "amount": float(
            convert_based_on_currency(
                order.get("amount", 0), conversion_factor, convert_to_lowest=False
            )
        ),  # Convert paise to rupees as we want to work in standard currency units in UI
        "amount_due": float(
            convert_based_on_currency(
                order.get("amount_due", 0), conversion_factor, convert_to_lowest=False
            )
        ),
    }


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
                "customer_id": str(
                    razorpay_order.notes.customer.id
                    if razorpay_order.notes.customer
                    else ""
                ),
                "customer_name": str(
                    razorpay_order.notes.customer.name
                    if razorpay_order.notes.customer
                    else ""
                ),
            },
        }
        client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
        order = client.order.create(data=order_data)
        if not order or "id" not in order:
            raise CabboException("Failed to create Razorpay order.", status_code=500)
        _formatted_order = _format_razorpay_order(
            order, razorpay_order.currency_conversion_factor
        )
        _formatted_order["currency_symbol"] = razorpay_order.currency_symbol
        logger.info(f"Razorpay order created successfully: {_formatted_order}")

        return _formatted_order
    except razorpay.errors.BadRequestError as e:
        logger.error(f"Razorpay order creation failed: {str(e)}")
        raise CabboException(
            f"Razorpay order creation failed: {str(e)}", status_code=500
        )
    except Exception as e:
        logger.error(f"Unexpected error during Razorpay order creation: {str(e)}")
        raise CabboException(
            f"Unexpected error during Razorpay order creation: {str(e)}",
            status_code=500,
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
            "customer_id": str(notes.customer.id if notes.customer else ""),
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
                id=customer.id,
                name=customer.name,
                email=customer.email or None,
                contact=customer.phone_number,
            ),
            requestor=temp_trip.creator_id,
        ),
    )
    trip_id = temp_trip.id  # Use the temporary trip ID as the booking ID
    return trip_id, _create_razorpay_order(razorpay_order=razorpay_schema)


def verify_razorpay_payment(payment_detail: dict):
    """
    Verify the payment status with Razorpay.
    This function should be called after the payment is completed to confirm the payment status.
    """
    client = RAZOR_PAY_CLIENT
    client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
    try:
        payment_detail = RazorPayPaymentResponse.model_validate(payment_detail)
        payment = client.payment.fetch(payment_detail.razorpay_payment_id)
        if payment["status"] == RazorPayPaymentStatusEnum.CAPTURED.value:
            logger.debug(
                f"Payment {payment_detail.razorpay_payment_id} verified successfully."
            )
            return True
        else:
            logger.error(
                f"Payment verification failed for {payment_detail.razorpay_payment_id}: Status is {payment['status']}"
            )
            return False
    except razorpay.errors.BadRequestError as e:
        logger.error(
            f"Payment verification failed for {payment_detail.razorpay_payment_id}: {str(e)}"
        )
        return False  # If there's an error, we assume payment verification failed

    except Exception as e:
        logger.error(
            f"Unexpected error during payment verification for {payment_detail.razorpay_payment_id}: {str(e)}"
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
    refund_data={}
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
                "customer_id": str(notes.customer.id if notes.customer else ""),
                "customer_name": str(notes.customer.name if notes.customer else ""),
            }

        # Guard: check if a refund already exists for this payment before initiating a new one
        # For Cabbo, a payment is always refunded once (full or partial) — this prevents duplicate refunds
        existing_refunds = client.payment.fetch_multiple_refund(payment_id)
        if existing_refunds and existing_refunds.get("items"):
            existing_refund = existing_refunds["items"][
                0
            ]  # Assuming only one refund per payment, take the first one
            logger.info(
                f"Refund already exists for payment {payment_id} with status {existing_refund.get('status')}, returning existing refund instead of initiating new one"
            )
            print(f"Refund already exists for payment {payment_id} with status {existing_refund.get('status')}, returning existing refund instead of initiating new one")
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

        logger.info(f"Razorpay refund initiated successfully: {formatted_refund}")
        return formatted_refund

    except razorpay.errors.BadRequestError as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Razorpay refund creation failed: {str(e)}")
        
        return _populate_failed_razorpay_refund_response(
            payment_id=payment_id,
            refund_amount=refund_amount,
            notes=notes,
            currency_conversion_factor=currency.lowest_unit_conversion_factor,
            currency_code=currency.code,
        )

    except Exception as e:
        logger.error(f"Unexpected error during Razorpay refund creation: {str(e)}")

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
        logger.warning(
            f"[razorpay_service] Skipping refund status check for {refund_id}: "
            f"no valid razorpay refund ID (got: {refund_id!r})"
        )
        return RazorPayRefundStatusEnum.FAILED  # Treat missing/invalid refund ID as failed status since there is nothing to poll
    
    client = RAZOR_PAY_CLIENT
    client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
    try:
        refund = client.refund.fetch(refund_id)
        status = refund.get("status")
        if status in RazorPayRefundStatusEnum._value2member_map_:
            return RazorPayRefundStatusEnum(status)
        else:
            logger.error(f"Unknown refund status received from Razorpay: {status}")
            return RazorPayRefundStatusEnum.FAILED  # Treat unknown status as failed
    except razorpay.errors.BadRequestError as e:
        logger.error(
            f"Failed to fetch Razorpay refund status for {refund_id}: {str(e)}"
        )
        return RazorPayRefundStatusEnum.FAILED  # Treat errors as failed status
    except Exception as e:
        logger.error(
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
        print(f"Payment details for settlement check: {payment}")
        settlement_id = payment.get("settlement_id", None)
        return settlement_id is not None  # If settlement_id is present, payment is settled
    except razorpay.errors.BadRequestError as e:
        logger.error(
            f"Failed to fetch Razorpay payment status for {payment_id}: {str(e)}"
        )
        return False  # Treat errors as not settled
    except Exception as e:
        logger.error(
            f"Unexpected error while fetching Razorpay payment status for {payment_id}: {str(e)}"
        )
        return False  # Treat unexpected errors as not settled

if __name__ == "__main__":
    # Quick test to verify Razorpay integration is working
    test_payment_id = "pay_SO51bSsBCz3BHV"  # Replace with a valid payment ID for testing
    print(is_razorpay_payment_settled(test_payment_id))