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
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_schema import TripBookRequest, TripDetails

logger = logging.getLogger(__name__)
APP_COUNTRY_CURRENCY = "INR"  # Placeholder for country currency, adjust as needed
RAZOR_PAY_CLIENT_DETAILS = {
    "version": APP_VERSION,
    "name": f"{APP_NAME.capitalize()} Trip Booking Service",
    "description": "Service for booking trips and managing payments.",
}


def _format_razorpay_order(order: dict) -> dict:
    """Format Razorpay order response."""
    return {
        **order,
        "amount": float(order.get("amount", 0) / 100),
        "amount_due": float(order.get("amount_due", 0) / 100),
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
        client = razorpay.Client(
            auth=(settings.RAZOR_PAY_KEY_ID, settings.RAZOR_PAY_KEY_SECRET)
        )

        order_data = {
            "description": razorpay_order.description,
            "amount": int(razorpay_order.amount * 100),  # Amount in paise
            "currency": razorpay_order.currency,
            "receipt": razorpay_order.receipt,
            "notes": razorpay_order.notes.model_dump(),
        }
        client.set_app_details(RAZOR_PAY_CLIENT_DETAILS)
        order = client.order.create(data=order_data)
        if not order or "id" not in order:
            raise CabboException("Failed to create Razorpay order.", status_code=500)
        _formatted_order = _format_razorpay_order(order)
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
    booking_request: TripBookRequest, customer: Customer, temp_trip: TempTrip
) -> tuple:
    razorpay_schema = RazorpayOrderSchema(
        description=f"Trip booking for {booking_request.preferences.trip_type} trip by {customer.name}",
        amount=temp_trip.platform_fee,  # Collect platform fee/convenience fee from the customer as part of the trip booking so that system is not abused
        currency=APP_COUNTRY_CURRENCY,
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
    booking_id = temp_trip.id  # Use the temporary trip ID as the booking ID
    return booking_id, _create_razorpay_order(razorpay_order=razorpay_schema)


def verify_payment(payment_detail: RazorPayPaymentResponse):
    """
    Verify the payment status with Razorpay.
    This function should be called after the payment is completed to confirm the payment status.
    """
    client = razorpay.Client(
        auth=(settings.RAZOR_PAY_KEY_ID, settings.RAZOR_PAY_KEY_SECRET)
    )
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
