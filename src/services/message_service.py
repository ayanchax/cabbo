from functools import lru_cache
import sys
from pathlib import Path
import asyncio

parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from twilio.rest import Client
from services.otp_service import OTP_EXPIRY_MINUTES, OTPFlow
from utils.redaction import mask_email, mask_phone
import sendgrid
import secrets
from email.utils import parseaddr
from sendgrid.helpers.mail import Mail
from datetime import datetime, timezone, timedelta
from jinja2 import Environment, FileSystemLoader, select_autoescape
from core.constants import Environment as AppEnvironment

import os
from email.message import EmailMessage
import aiosmtplib
from core.config import settings
from core.constants import APP_NAME, PROJECT_ROOT
from core.sentry import capture_email_send_failure, capture_otp_send_failure
import logging
import requests

log = logging.getLogger(__name__)
EMAIL_VERIFY_EXPIRY_UNIT = 2
EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME = {
    "DAYS": "days",
    "HOURS": "hours",
    "MINUTES": "minutes",
}

# MSG91 Configuration
MSG_91_SEND_SMS_URL = "https://control.msg91.com/api/v5/flow"
BREVO_API_SEND_EMAIL_URL = "https://api.brevo.com/v3/smtp/email"

# Twilio Configuration for sending SMS
TWILIO_ACCOUNT_SID = settings.TWILLIO_ACCOUNT_SID
TWILIO_AUTH_TOKEN = settings.TWILLIO_AUTH_TOKEN
TWILIO_FROM_NUMBER = settings.TWILLIO_PHONE_NUMBER

client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# SendGrid Configuration for sending Emails
SENDGRID_API_KEY = settings.SENDGRID_API_KEY
sg_client = sendgrid.SendGridAPIClient(api_key=SENDGRID_API_KEY)

WELCOME_EMAIL_FILE = "welcome.html"
EMAIL_VERIFICATION_FILE = "email_verification.html"
# Jinja2 Environment for email templates
EMAIL_TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates", "emails")


jinja_templates_env = Environment(
    loader=FileSystemLoader(EMAIL_TEMPLATES_DIR),
    autoescape=select_autoescape(["html", "xml"]),
)

# Twilio Text Messaging Service


def send_otp(to_number: str, message="Hello world", **kwargs) -> bool:
    """
    Send OTP using Twilio. Returns True if sent, False otherwise.
    """

    if settings.SMS_SERVICE_PROVIDER.lower() == "twilio":
        return _send_twilio_sms(to_number, message)
    elif settings.SMS_SERVICE_PROVIDER.lower() == "mock":
        return _send_mock_sms(to_number, message)
    elif settings.SMS_SERVICE_PROVIDER.lower() == "msg91":
        return _send_msg91_sms(to_number, **kwargs)

    else:
        log.error(f"Unsupported SMS service provider: {settings.SMS_SERVICE_PROVIDER}")
        capture_otp_send_failure(
            provider=settings.SMS_SERVICE_PROVIDER.lower(),
            failure_type="unsupported_provider",
        )
        return False


@lru_cache(maxsize=2000)
def _get_dlt_template_id(flow: OTPFlow):
    if flow == OTPFlow.REGISTRATION:
        return settings.REGISTRATION_OTP_DLT_TEMPLATE_ID
    if flow == OTPFlow.LOGIN:
        return settings.LOGIN_OTP_DLT_TEMPLATE_ID
    if flow == OTPFlow.RESEND:
        return settings.RESEND_OTP_DLT_TEMPLATE_ID
    return None


def _send_msg91_sms(to_number: str, **config):

    def _format_msg91_phone_number(phone_number: str) -> str:
        """
        Convert an E.164 standard(Numbering plan of the international telephone service) phone number into the format expected by MSG91.

        Example:
            +919831305667 -> 919831305667
            +91 9831305667 -> 919831305667
        """
        return phone_number.replace("+", "").replace(" ", "")

    try:
        flow: OTPFlow = config.get(
            "flow", None
        )  # Since MSG91 needs template id based on the message flow, we will evaluate the template_id based on the flow.
        if not flow:
            log.error(
                "MSG91 SMS send skipped for %s: missing flow", mask_phone(to_number)
            )
            return False
        template_id = _get_dlt_template_id(flow=flow)
        if not template_id:
            log.error(
                "MSG91 SMS send skipped for %s: missing template id for flow %s",
                mask_phone(to_number),
                flow,
            )
            return False
        otp = config.get("otp", None)
        if not otp:
            log.error(
                "MSG91 SMS send skipped for %s: missing otp", mask_phone(to_number)
            )
            return False
        expires_in = config.get("expires_in", str(OTP_EXPIRY_MINUTES))
        formatted_msg91_phone_number = _format_msg91_phone_number(
            phone_number=to_number
        )
        payload = {
            "template_id": template_id,
            "short_url": "0",
            "recipients": [
                {
                    "mobiles": formatted_msg91_phone_number,
                    "number1": otp,
                    "number2": expires_in,
                }
            ],
        }
        headers = {
            "accept": "application/json",
            "authkey": settings.SMS_PROVIDER_AUTHKEY,
            "content-type": "application/json",
        }
        response = requests.post(
            url=MSG_91_SEND_SMS_URL,
            json=payload,
            headers=headers,
            timeout=10,
        )
        if 200 <= response.status_code < 300:
            data = response.json()

            log.info(
                "MSG91 accepted OTP for %s. response=%s",
                mask_phone(to_number),
                data,
            )
            return True

        log.error(
            "MSG91 SMS send failed for %s with status %s: %s",
            mask_phone(to_number),
            response.status_code,
            response.text[:500],
        )
        capture_otp_send_failure(
            provider="msg91",
            failure_type=f"http_{response.status_code}",
        )
        return False
    except Exception as e:
        log.error(
            f"MSG91 SMS send failed for {mask_phone(to_number)}: " f"{type(e).__name__}"
        )
        capture_otp_send_failure(
            provider="msg91",
            failure_type=type(e).__name__,
        )
        return False


def _send_mock_sms(to_number: str, message: str) -> bool:
    """
    Mock SMS sending for testing purposes. Always returns True.
    """
    if settings.ENV == AppEnvironment.LOCAL.value:
        log.info(
            f"Mock SMS generated for {mask_phone(to_number)} with message: {message}"
        )
    else:
        log.info(f"Mock SMS generated for {mask_phone(to_number)}")
    return True


def _send_twilio_sms(to_number: str, message: str) -> bool:
    """
    Send an SMS using Twilio. Returns True if sent, raises CabboException otherwise.
    """
    try:
        client.messages.create(body=message, from_=TWILIO_FROM_NUMBER, to=to_number)
        return True
    except Exception as e:
        log.error(
            f"Twilio SMS send failed for {mask_phone(to_number)}: "
            f"{type(e).__name__}"
        )
        capture_otp_send_failure(
            provider="twilio",
            failure_type=type(e).__name__,
        )
        # Log the error and delete OTP from temp table if sending fails
        return False


async def send_email(
    to_email: str, subject: str, html_content: str, from_email: str = None
) -> bool:
    """
    Send an email using the configured email service provider.
    """
    email_provider = settings.EMAIL_SERVICE_PROVIDER.lower()
    if email_provider == "sendgrid":
        return _sendgrid_send_email(to_email, subject, html_content, from_email)
    elif email_provider == "aws_ses":
        return await _aws_ses_send_email(to_email, subject, html_content, from_email)
    elif email_provider == "brevo":
        return await _brevo_send_email(to_email, subject, html_content, from_email)
    else:
        log.error(f"Unsupported email service provider: {email_provider}")
        return False


async def _brevo_send_email(
    to_email: str, subject: str, html_content: str, from_email: str = None
):
    # 300 emails per day - free
    if not from_email:
        from_email = settings.BREVO_FROM_NO_REPLY_EMAIL
    if settings.BREVO_API_KEY:
        # Send email using API
        return await asyncio.to_thread(
            _send_brevo_email_via_api,
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            from_email=from_email,
        )
    # Send email using Brevo SMTP SDK.
    try:
        message = EmailMessage()
        message["From"] = from_email
        message["To"] = to_email
        message["Subject"] = subject

        message.set_content("This email requires an HTML-capable email client.")
        message.add_alternative(html_content, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=settings.BREVO_SMTP_HOST,
            port=settings.BREVO_SMTP_PORT,
            start_tls=settings.BREVO_SMTP_PORT != 465,
            use_tls=settings.BREVO_SMTP_PORT == 465,
            username=settings.BREVO_SMTP_USERNAME,
            password=settings.BREVO_SMTP_PASSWORD,
            timeout=20,
        )
        log.info(f"Brevo email sent to {mask_email(to_email)}")
        return True

    except Exception as e:
        log.error(
            f"Brevo email send failed for {mask_email(to_email)}: "
            f"{type(e).__name__}"
        )
        capture_email_send_failure(
            provider="brevo",
            failure_type=type(e).__name__,
        )
        return False


def _send_brevo_email_via_api(
    to_email: str, subject: str, html_content: str, from_email: str
) -> bool:
    sender_name, sender_email = parseaddr(from_email or "")
    if not sender_email:
        log.error("Brevo API email send skipped: missing sender email")
        return False

    payload = {
        "sender": {
            "name": sender_name or APP_NAME.capitalize(),
            "email": sender_email,
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content,
    }
    headers = {
        "accept": "application/json",
        "api-key": settings.BREVO_API_KEY,
        "content-type": "application/json",
    }

    try:
        response = requests.post(
            BREVO_API_SEND_EMAIL_URL,
            json=payload,
            headers=headers,
            timeout=20,
        )
        if 200 <= response.status_code < 300:
            data = response.json()
            log.info(
                "Brevo API email accepted for %s. message_id=%s",
                mask_email(to_email),
                data.get("messageId"),
            )
            return True

        log.error(
            "Brevo API email send failed for %s with status %s",
            mask_email(to_email),
            response.status_code,
        )
        capture_email_send_failure(
            provider="brevo",
            failure_type=f"http_{response.status_code}",
        )
        return False
    except Exception as e:
        log.error(
            f"Brevo API email send failed for {mask_email(to_email)}: "
            f"{type(e).__name__}"
        )
        capture_email_send_failure(
            provider="brevo",
            failure_type=type(e).__name__,
        )
        return False


def _sendgrid_send_email(
    to_email: str, subject: str, html_content: str, from_email: str = None
):
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
        log.info(
            f"SendGrid email sent to {mask_email(to_email)} with status code {response.status_code}"
        )
        return 200 <= response.status_code < 300
    except Exception as e:
        # We will log audit logs later on failures of email sending
        log.error(
            f"SendGrid email send failed for {mask_email(to_email)}: "
            f"{type(e).__name__}"
        )
        return False


async def _aws_ses_send_email(
    to_email: str,
    subject: str,
    html_content: str,
    from_email: str | None = None,
) -> bool:
    if not from_email:
        from_email = settings.AWS_SES_FROM_NO_REPLY_EMAIL

    try:
        message = EmailMessage()
        message["From"] = from_email
        message["To"] = to_email
        message["Subject"] = subject

        message.set_content("This email requires an HTML-capable email client.")
        message.add_alternative(html_content, subtype="html")

        await aiosmtplib.send(
            message,
            hostname=settings.AWS_SES_SMTP_HOST,
            port=settings.AWS_SES_SMTP_PORT,
            start_tls=True,
            username=settings.AWS_SES_SMTP_USERNAME,
            password=settings.AWS_SES_SMTP_PASSWORD,
            timeout=20,
        )
        log.info(f"AWS SES email sent to {mask_email(to_email)}")
        return True

    except Exception as e:
        # We will log audit logs later on failures of email sending
        log.error(
            f"AWS SES email send failed for {mask_email(to_email)}: "
            f"{type(e).__name__}"
        )
        return False


def render_email_template(
    template_name: str,
    for_customer=False,
    for_driver=False,
    include_year=True,
    **kwargs,
) -> str:
    """
    Render an email template with the given context.
    """
    if for_customer:
        template_name = f"customer/{template_name}"
    elif for_driver:
        template_name = f"driver/{template_name}"

    template = jinja_templates_env.get_template(template_name)
    if include_year:
        now = datetime.now(timezone.utc)
        kwargs["current_year"] = now.year

    kwargs["app_logo_url"] = settings.APP_LOGO_URL

    if "app_name" not in kwargs:
        kwargs["app_name"] = APP_NAME.capitalize()

    if "app_url" not in kwargs:
        kwargs["app_url"] = settings.APP_URL

    return template.render(**kwargs)


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
    verification_url = f"{settings.APP_URL}/verify-email?ep={endpoint}&id={id}&token={secrets.token_urlsafe(16)}"
    return verification_url, expiry
