from core.constants import APP_COUNTRY_CURRENCY, APP_NAME, APP_VERSION
from core.exceptions import CabboException
from models.customer.customer_orm import Customer
from models.customer.customer_schema import CustomerPayment
from models.financial.payments_schema import PaymentNotesSchema, RazorpayOrderSchema
from sqlalchemy.orm import Session
import razorpay
from core.config import settings
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_schema import TripBookRequest
from services.passenger_service import get_passenger_id_from_preferences

def _create_razorpay_order(
    razorpay_order: RazorpayOrderSchema, db:Session=None
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
        client.set_app_details({
            "version": APP_VERSION,
            "name": f"{APP_NAME.capitalize()} Trip Booking Service",
            "description": "Service for booking trips and managing payments."
        })
        order = client.order.create(data=order_data)
        if not order or "id" not in order:
            raise CabboException("Failed to create Razorpay order.", status_code=500)
        return order
    except razorpay.errors.RazorpayError as e:
        raise CabboException(
            f"Razorpay error: {str(e)}", status_code=500, include_traceback=True
        )

def get_trip_payment_order(booking_request:TripBookRequest, customer:Customer, temp_trip:TempTrip) -> tuple:
    razorpay_schema = RazorpayOrderSchema(
        description=f"Trip booking for {booking_request.preferences.trip_type} trip by {customer.name}",
        amount=temp_trip.platform_fee, #Collect platform fee from the customer as part of the trip booking so that system is not abused
        currency=APP_COUNTRY_CURRENCY,
        receipt=f"id#{temp_trip.id}",
        notes=PaymentNotesSchema(
            reference_source_id=temp_trip.id,
            customer=CustomerPayment(id=customer.id,name=customer.name, email=customer.email or None, contact=customer.phone_number),
            trip_type_id=temp_trip.trip_type_id,
            requestor=temp_trip.creator_id,
            passenger_id=get_passenger_id_from_preferences(preferences=booking_request.preferences),
            )
    )
    booking_id =temp_trip.id  # Use the temporary trip ID as the booking ID
    return booking_id, _create_razorpay_order(
        razorpay_order=razorpay_schema
    )
    