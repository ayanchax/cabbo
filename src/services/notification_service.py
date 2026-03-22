from core.constants import APP_NAME
from core.security import RoleEnum
from db.database import get_mysql_local_session
from models.customer.customer_schema import CustomerRead
from models.driver.driver_orm import Driver
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import Trip
from sqlalchemy.orm import Session
from core.config import settings
from services.message_service import (
    EMAIL_VERIFICATION_FILE,
    EMAIL_VERIFY_EXPIRY_UNIT,
    WELCOME_EMAIL_FILE,
    render_email_template,
    send_email,
)
from services.trips.airport_transfers_service import get_kwargs_for_airport_transfer
from services.trips.local_hourly_rental_service import (
    get_kwargs_for_local_hourly_rental,
)
from services.trips.outstation_service import get_kwargs_for_outstation_trip

db = get_mysql_local_session()


async def notify_customer_booking_confirmed(booking: Trip) -> bool:
    creator_type = booking.creator_type
    if creator_type != RoleEnum.customer.value:
        return False
    customer_id = booking.creator_id
    if not customer_id:
        return False
    customer = (
        booking.customer
        if booking.creator_id and booking.creator_type == "customer"
        else None
    )
    customer = CustomerRead.model_validate(customer) if customer else None
    if not customer:
        return False
    if not customer.email:
        return False  # No email to send notification, do not proceed
    if not booking.trip_type_id:
        return False
    trip_type = (
        booking.trip_type_master.trip_type
        if hasattr(booking.trip_type_master, "trip_type")
        else None
    )
    if not trip_type:
        return False
    config_store = settings.get_config_store(db)

    if trip_type == TripTypeEnum.local:
        # Notify customer about cab booking confirmation
        attrs = get_kwargs_for_local_hourly_rental(
            trip=booking,
            currency=config_store.geographies.country_server.currency_symbol,
            customer=customer,
        )
        if not attrs:
            return False
        if attrs.get("customer_email"):
            html_content = render_email_template(
                "hourly_local_rental_booking_confirmation.html",
                for_customer=True,
                **attrs,
            )
            # Won't block the main flow for email sending failure. as it is running asynchronously in background
            await send_email(
                to_email=attrs["customer_email"],
                subject="Your Cabbo Booking is Confirmed!",
                html_content=html_content,
            )
            return True

    elif trip_type == TripTypeEnum.outstation:
        # Notify customer about cab booking confirmation
        attrs = get_kwargs_for_outstation_trip(
            trip=booking,
            currency=config_store.geographies.country_server.currency_symbol,
            customer=customer,
        )
        if not attrs:
            return False
        if attrs.get("customer_email"):
            html_content = render_email_template(
                "outstation_booking_confirmation.html",
                for_customer=True,
                **attrs,
            )
            # Won't block the main flow for email sending failure. as it is running asynchronously in background
            await send_email(
                to_email=attrs["customer_email"],
                subject="Your Cabbo Booking is Confirmed!",
                html_content=html_content,
            )
            return True
    elif trip_type in [TripTypeEnum.airport_drop, TripTypeEnum.airport_pickup]:
        # Notify customer about cab booking confirmation
        attrs = get_kwargs_for_airport_transfer(
            trip_type=trip_type,
            trip=booking,
            currency=config_store.geographies.country_server.currency_symbol,
            customer=customer,
        )
        if not attrs:
            return False
        if attrs.get("customer_email"):
            html_content = render_email_template(
                "airport_transfer_booking_confirmation.html",
                for_customer=True,
                **attrs,
            )
            # Won't block the main flow for email sending failure. as it is running asynchronously in background
            await send_email(
                to_email=attrs["customer_email"],
                subject="Your Cabbo Booking is Confirmed!",
                html_content=html_content,
            )
            return True
    else:
        print(f"Unsupported trip type for notification: {trip_type}")
    return False


def notify_customer_onboarded(customer: CustomerRead) -> bool:
    if not customer.email:
        return False  # No email to send notification, do not proceed
    name = customer.name if customer.name else customer.email.split("@")[0]
    subject = f"Welcome to {APP_NAME}!"
    html_content = render_email_template(
        WELCOME_EMAIL_FILE,
        for_customer=True,
        name=name,
        app_name=APP_NAME.capitalize(),
        app_url=settings.APP_URL,
    )
    # Won't block the main flow for email sending failure. as it is running asynchronously in background
    send_email(
        to_email=customer.email,
        subject=subject,
        html_content=html_content,
    )


def notify_driver_onboarded(driver: Driver) -> bool:
    if not driver.email:
        return False  # No email to send notification, do not proceed

    name = driver.name if driver.name else driver.email.split("@")[0]
    subject = f"Welcome to {APP_NAME}!"

    html_content = render_email_template(
        WELCOME_EMAIL_FILE,
        for_driver=True,
        name=name,
        app_name=APP_NAME.capitalize(),
    )
    # Won't block the main flow for email sending failure. as it is running asynchronously in background
    send_email(
        to_email=driver.email,
        subject=subject,
        html_content=html_content,
    )
    return True


async def notify_verification_email_to_customer(
    customer: CustomerRead, verification_url: str
) -> bool:
    subject = f"Verify your email for {APP_NAME.capitalize()}"
    if not customer:
        return False
    if not customer.email:
        return False  # No email to send notification, do not proceed
    name = customer.name if customer.name else customer.email.split("@")[0]
    html_content = render_email_template(
        EMAIL_VERIFICATION_FILE,
        for_customer=True,
        name=name,
        verification_link=verification_url,
        expiry_hours=str(EMAIL_VERIFY_EXPIRY_UNIT),
        app_name=APP_NAME.capitalize(),
        app_url=settings.APP_URL,
    )
    # Won't block the main flow for email sending failure. as it is running asynchronously in background
    await send_email(
        to_email=customer.email,
        subject=subject,
        html_content=html_content,
    )
    return True



async def notify_refund_initiated_to_customer(
    customer: CustomerRead,
    refund_id: str,
    refund_amount: float,
    refund_type: str,
    currency: str,
    booking_id: str,
    original_amount: float,
    currency_position: str = "before",
    
) -> bool:
    subject = f"Yay! Your Refund for {APP_NAME.capitalize()} Booking is on its Way!"
    if not customer:
        return False
    if not customer.email:
        return False  # No email to send notification, do not proceed
    name = customer.name if customer.name else customer.email.split("@")[0]
    html_content = render_email_template(
        "refund-initiated-on-trip-cancellation.html",
        for_customer=True,
        name=name,
        refund_id=refund_id,
        currency=currency,
        original_amount=original_amount,
        refund_amount=refund_amount,
        refund_type=refund_type,
        booking_id=booking_id,
        currency_position=currency_position,
    )
    # Won't block the main flow for email sending failure. as it is running asynchronously in background
    await send_email(
        to_email=customer.email,
        subject=subject,
        html_content=html_content,
    )
    return True

async def notify_refund_processed_to_customer(
    customer: CustomerRead,
    refund_id: str,
    refund_amount: float,
    original_amount: float,
    refund_type: str,
    booking_id: str,
    currency: str,
    currency_position: str = "before",
) -> bool:
    subject = f"Good news! Your Refund for {APP_NAME.capitalize()} Booking has been processed!"
    if not customer:
        return False
    if not customer.email:
        return False  # No email to send notification, do not proceed
    name = customer.name if customer.name else customer.email.split("@")[0]
    html_content = render_email_template(
        "refund-processed.html",
        for_customer=True,
        name=name,
        refund_id=refund_id,
        refund_amount=refund_amount,
        original_amount=original_amount,
        refund_type=refund_type,
        booking_id=booking_id,
        currency=currency,
        currency_position=currency_position,
        app_name=APP_NAME.capitalize(),
    )
    # Won't block the main flow for email sending failure. as it is running asynchronously in background
    await send_email(
            to_email=customer.email,
            subject=subject,
            html_content=html_content,
        )
    return True