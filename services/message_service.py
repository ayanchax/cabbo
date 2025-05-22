from twilio.rest import Client
from core.config import settings
from core.constants import APP_NAME
import sendgrid
from sendgrid.helpers.mail import Mail

# Twilio Configuration
TWILIO_ACCOUNT_SID = settings.TWILLIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN = settings.TWILLIO_AUTH_TOKEN
TWILIO_FROM_NUMBER = settings.TWILLIO_PHONE_NUMBER

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Twilio Text Messaging Service

def send_otp(to_number: str, otp: str, expiry="5 minutes") -> bool:
    """
    Send OTP using Twilio. Returns True if sent, False otherwise.
    """
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to complete your registration. This OTP is valid for {expiry}."
    return send_sms(to_number, message)

def send_sms(to_number: str, message: str) -> bool:
    """
    Send an SMS using Twilio. Returns True if sent, raises CabboException otherwise.
    """
    try:
        client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=to_number
        )
        return True
    except Exception as e:
        # Log the error and delete OTP from temp table if sending fails
        return False

def send_email(to_email: str, subject: str, html_content: str, from_email: str = None) -> bool:
    """
    Send an email using SendGrid. Returns True if sent, False otherwise.
    """
    sg_api_key = settings.SENDGRID_API_KEY
    if not from_email:
        from_email = settings.SENDGRID_FROM_EMAIL
    try:
        sg = sendgrid.SendGridAPIClient(api_key=sg_api_key)
        message = Mail(
            from_email=from_email,
            to_emails=to_email,
            subject=subject,
            html_content=html_content
        )
        response = sg.send(message)
        return 200 <= response.status_code < 300
    except Exception as e:
        print(f"SendGrid email send failed: {e}")
        return False