from core.constants import APP_NAME
from core.security import RoleEnum
from core.trip_helpers import get_trip_type_by_trip_type_id
from models.customer.customer_schema import CustomerRead
from models.driver.driver_orm import Driver
from models.trip.trip_enums import TripTypeEnum
from models.trip.trip_orm import Trip
from sqlalchemy.orm import Session
from core.config import settings
from services.customer_service import get_customer_by_id
from services.message_service import EMAIL_VERIFICATION_FILE, EMAIL_VERIFY_EXPIRY_UNIT, WELCOME_EMAIL_FILE, render_email_template, send_email
from services.trips.airport_transfers_service import get_kwargs_for_airport_transfer
from services.trips.local_hourly_rental_service import (
    get_kwargs_for_local_hourly_rental,
)
from services.trips.outstation_service import get_kwargs_for_outstation_trip


async def notify_customer_booking_confirmed(booking: Trip, db: Session) -> bool:
    creator_type = booking.creator_type
    if creator_type != RoleEnum.customer.value:
        return False
    customer_id = booking.creator_id
    if not customer_id:
        return False
    customer = get_customer_by_id(customer_id, db)
    if not customer:
        return False
    if not customer.email:
        return False  # No email to send notification, do not proceed
    if not booking.trip_type_id:
        return False
    trip_type = get_trip_type_by_trip_type_id(booking.trip_type_id, db=db)
    if not trip_type:
        return False
    config_store = settings.get_config_store(db)
    if trip_type == TripTypeEnum.local:
        # Notify customer about cab booking confirmation
        attrs = get_kwargs_for_local_hourly_rental(
            trip=booking,
            currency=config_store.geographies.country_server.currency_symbol,
            db=db,
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
            db=db,
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
            db=db,
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
    return False

def notify_customer_onboarded(customer:CustomerRead) -> bool:
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
    

def notify_driver_onboarded(driver:Driver) -> bool:
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

async def notify_verification_email_to_customer(customer:CustomerRead, verification_url:str) -> bool:
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