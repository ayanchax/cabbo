from twilio.rest import Client
from core.config import settings
import sendgrid
import secrets
from sendgrid.helpers.mail import Mail
from datetime import datetime, timezone, timedelta

EMAIL_VERIFY_EXPIRY_UNIT = 2
EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME = {
    "DAYS": "days",
    "HOURS": "hours",
    "MINUTES": "minutes",
}

# Twilio Configuration for sending SMS
TWILIO_ACCOUNT_SID = settings.TWILLIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN = settings.TWILLIO_AUTH_TOKEN
TWILIO_FROM_NUMBER = settings.TWILLIO_PHONE_NUMBER

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# SendGrid Configuration for sending Emails
SENDGRID_API_KEY = settings.SENDGRID_API_KEY
sg_client = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)

# Twilio Text Messaging Service


def send_otp(to_number: str, message="Hello world") -> bool:
    """
    Send OTP using Twilio. Returns True if sent, False otherwise.
    """

    return send_sms(to_number, message)


def send_sms(to_number: str, message: str) -> bool:
    """
    Send an SMS using Twilio. Returns True if sent, raises CabboException otherwise.
    """
    try:
        client.messages.create(body=message, from_=TWILIO_FROM_NUMBER, to=to_number)
        return True
    except Exception as e:
        # Log the error and delete OTP from temp table if sending fails
        return False


def send_email(
    to_email: str, subject: str, html_content: str, from_email: str = None
) -> bool:
    """
    Send an email using SendGrid. Returns True if sent, False otherwise.
    """
    if not from_email:
        from_email = settings.SENDGRID_FROM_NO_REPLY_EMAIL
    try:
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html_content,
        )
        response = sg_client.send(message)
        return 200 <= response.status_code < 300
    except Exception as e:
        print(f"SendGrid email send failed: {e}")
        return False


def create_email_verification_link(
    id: str,
    endpoint: str,
    expires_in=EMAIL_VERIFY_EXPIRY_UNIT,
    expires_unit=EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME.get("HOURS"),
) -> tuple:
    """
    Create a verification link for email verification.
    """
    now = datetime.now(timezone.utc)
    if expires_unit == EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME.get("DAYS"):
        expiry = now + timedelta(days=expires_in)
    elif expires_unit == EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME.get("HOURS"):
        expiry = now + timedelta(hours=expires_in)
    elif expires_unit == EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME.get("MINUTES"):
        expiry = now + timedelta(minutes=expires_in)
    else:
        expiry = now + timedelta(hours=EMAIL_VERIFY_EXPIRY_UNIT)  # fallback
    verification_url = (
        f"{settings.API_URL}{endpoint}?id={id}&token={secrets.token_urlsafe(16)}"
    )
    return verification_url, expiry
