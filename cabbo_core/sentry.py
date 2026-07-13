import logging
import re
from typing import Any
import sentry_sdk
log = logging.getLogger(__name__)


REDACTED = "[Filtered]"

SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "contact",
    "cookie",
    "email",
    "jwt",
    "order_id",
    "otp",
    "password",
    "payment_id",
    "phone",
    "phone_number",
    "razorpay_order_id",
    "razorpay_payment_id",
    "razorpay_signature",
    "refresh_token",
    "refund_id",
    "secret",
    "session",
    "signature",
    "token",
    "x-razorpay-signature",
}

EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")
OTP_RE = re.compile(r"\b(?:otp|one[-\s]?time[-\s]?password)\b[:=\s-]*\d{4,8}", re.IGNORECASE)
RAZORPAY_ID_RE = re.compile(r"\b(?:order|pay|rfnd)_[A-Za-z0-9]{8,}\b")
JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b")


def _is_sensitive_key(key: str) -> bool:
    normalized_key = key.lower().replace("-", "_")
    return any(sensitive_key in normalized_key for sensitive_key in SENSITIVE_KEYS)


def _scrub_string(value: str) -> str:
    value = EMAIL_RE.sub(REDACTED, value)
    value = PHONE_RE.sub(REDACTED, value)
    value = OTP_RE.sub(REDACTED, value)
    value = RAZORPAY_ID_RE.sub(REDACTED, value)
    value = JWT_RE.sub(REDACTED, value)
    return value


def scrub_sentry_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if _is_sensitive_key(str(key)) else scrub_sentry_data(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub_sentry_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub_sentry_data(item) for item in value)
    if isinstance(value, str):
        return _scrub_string(value)
    return value


def before_send(event: dict, hint: dict) -> dict:
    return scrub_sentry_data(event)




def capture_otp_rate_limit_hit(
    limit_type: str,
    retry_after_seconds: int,
    current_count: int,
    configured_limit: int,
    window_seconds: int,
    **kwargs
) -> None:
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("feature", "otp")
        scope.set_tag("otp.event", "rate_limit_hit")
        scope.set_tag("otp.limit_type", limit_type)
        scope.set_tag("otp.provider", kwargs.get("sms_provider","").lower())
        scope.set_context(
            "otp_rate_limit",
            {
                "current_count": current_count,
                "configured_limit": configured_limit,
                "retry_after_seconds": retry_after_seconds,
                "window_seconds": window_seconds,
            },
        )
        scope.capture_message("OTP rate limit hit", level="warning")


def capture_otp_send_failure(provider: str, failure_type: str) -> None:
    with sentry_sdk.new_scope() as scope:
        scope.set_tag("feature", "otp")
        scope.set_tag("otp.event", "send_failure")
        scope.set_tag("otp.provider", provider)
        scope.set_tag("otp.failure_type", failure_type)
        scope.capture_message("OTP send failure", level="error")
