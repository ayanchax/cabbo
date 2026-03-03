import logging
from typing import Literal

import razorpay.errors
from core.constants import APP_NAME, APP_VERSION
from core.exceptions import CabboException
from models.customer.customer_orm import Customer
from models.customer.customer_schema import CustomerPayment, CustomerRead
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
from models.trip.trip_schema import TripBookRequest, TripDetails

logger = logging.getLogger(__name__)

RAZOR_PAY_CLIENT = razorpay.Client(
    auth=(settings.RAZOR_PAY_KEY_ID, settings.RAZOR_PAY_KEY_SECRET)
)
RAZOR_PAY_CLIENT_DETAILS = {
    "version": APP_VERSION,
    "name": f"{APP_NAME.capitalize()} Trip Booking Service",
    "description": "Service for booking trips and managing payments.",
}


def _conversion_based_on_currency(
    amount: float, conversion_factor: int, convert_to_lowest: bool = True
) -> float:
    """Convert the amount based on the currency's conversion factor.
    Args:
        amount (float): The original amount in standard currency units (e.g., rupees).
        conversion_factor (int): The conversion factor for the currency.
        convert_to_lowest (bool): Whether to convert to the lowest currency unit (default is True).
    Returns:
        float: The converted amount in the smallest currency unit (e.g., paise).
    """
    if conversion_factor and conversion_factor > 0:
        if convert_to_lowest:
            return amount * conversion_factor
        else:
            # If convert_to_lowest is False, it means we want to convert from the lowest unit to the standard unit, so we divide by the conversion factor
            return amount / conversion_factor
    else:
        logger.warning(
            f"Invalid conversion factor. Using original amount without conversion."
        )
        return amount


def _format_razorpay_order(order: dict, conversion_factor: int) -> dict:
    """Format Razorpay order response."""
    return {
        **order,
        "amount": float(
            _conversion_based_on_currency(
                order.get("amount", 0), conversion_factor, convert_to_lowest=False
            )
        ),  # Convert paise to rupees as we want to work in standard currency units in UI
        "amount_due": float(
            _conversion_based_on_currency(
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
                _conversion_based_on_currency(
                    razorpay_order.amount, razorpay_order.currency_conversion_factor
                )
            ),  # Amount in paise as Razorpay expects amount in the smallest currency unit
            "currency": razorpay_order.currency,
            "receipt": razorpay_order.receipt,
            "notes": razorpay_order.notes.model_dump(),
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


def get_trip_payment_order(
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


def verify_payment(payment_detail: RazorPayPaymentResponse):
    """
    Verify the payment status with Razorpay.
    This function should be called after the payment is completed to confirm the payment status.
    """
    client = RAZOR_PAY_CLIENT
    client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
    try:
        payment = client.payment.fetch(payment_detail.razorpay_payment_id)
        if payment["status"] == "captured":
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


def attach_trip_details_to_order_notes(order: dict, trip_details: TripDetails):

    notes = order.get("notes", {})
    notes = PaymentNotesSchema.model_validate(notes)  # Validate the notes structure
    # Ensure that trip_details is set in notes
    if not hasattr(notes, "trip_details"):
        notes.trip_details = trip_details

    order["notes"] = notes.model_dump(
        exclude_none=True
    )  # Update the order with the notes containing trip details


def initiate_razorpay_refund(
    payment_id: str,
    refund_amount: float,
    notes:PaymentNotesSchema,
    currency_conversion_factor: int = 100,
    speed: Literal["normal", "optimum"] = "normal",
    silently_fail: bool = False,
) -> dict:
    """
    Initiate a refund for a Razorpay payment.

    Args:
        payment_id (str): The Razorpay payment ID to refund.
        refund_amount (float): The amount to refund in rupees.
        trip_id (str): The ID of the trip associated with the refund.
        customer (CustomerRead): The customer details associated with the refund.
        currency_conversion_factor (int): The conversion factor for the currency (e.g., 100 for INR to convert rupees to paise).
        speed (str): The speed of the refund, either "normal" or "optimum". "optimum" may result in faster refunds but may have additional costs.

    Returns:
        dict: A dictionary containing the refund details.
    """
    try:
        client = RAZOR_PAY_CLIENT
        client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)

        refund_data = {
            "amount": int(
                _conversion_based_on_currency(refund_amount, currency_conversion_factor)
            ),  # Convert rupees to paise
            "speed": speed,  # Can be 'normal' or 'optimum'
        }

        if notes:
            refund_data["notes"] = notes.model_dump(exclude_none=True)

         

        refund = client.payment.refund(payment_id, refund_data)

        if not refund or "id" not in refund:
            raise CabboException("Failed to create Razorpay refund.", status_code=500)

        # Format the refund response
        formatted_refund = {
            **refund,
            "amount": float(
                _conversion_based_on_currency(
                    refund.get("amount", 0),
                    currency_conversion_factor,
                    convert_to_lowest=False,
                )
            ),  # Convert paise to rupees
        }

        logger.info(f"Razorpay refund initiated successfully: {formatted_refund}")
        return formatted_refund

    except razorpay.errors.BadRequestError as e:
        logger.error(f"Razorpay refund creation failed: {str(e)}")
        if not silently_fail:
            raise CabboException(
                f"Razorpay refund creation failed: {str(e)}", status_code=500
            )
        return None
    except Exception as e:
        logger.error(f"Unexpected error during Razorpay refund creation: {str(e)}")
        if not silently_fail:
            raise CabboException(
                f"Unexpected error during Razorpay refund creation: {str(e)}",
                status_code=500,
            )
        return None
