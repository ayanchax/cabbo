from twilio.rest import Client
from core.config import settings
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
    message = f"Your OTP is {otp}. Please use it to complete your registration. This OTP is valid for {expiry}."
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