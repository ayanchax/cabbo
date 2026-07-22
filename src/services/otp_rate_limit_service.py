import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from fastapi import Request

from core.config import settings
from core.constants import Environment
from core.exceptions import OTP_RATE_LIMITED, CabboException
from core.sentry import capture_otp_rate_limit_hit
from utils.redaction import mask_phone


log = logging.getLogger(__name__)

_lock = Lock()
_phone_events: dict[str, deque[datetime]] = defaultdict(deque)
_ip_events: dict[str, deque[datetime]] = defaultdict(deque)
_phone_daily_events: dict[str, deque[datetime]] = defaultdict(deque)


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for") if request else None
    if forwarded_for:
        return forwarded_for.split(",", 1)[0].strip()
    if request and request.client:
        return request.client.host
    return "unknown"


def _prune(events: deque[datetime], cutoff: datetime) -> None:
    while events and events[0] <= cutoff: #Deque is ordered as oldest to newest, so we keep popping from the left as and when we have a new cutoff time which is greater than the oldest event in the deque. This ensures that we only keep events that are within the relevant time window for rate limiting.
        events.popleft() # Remove events that are older than the cutoff time


def _seconds_until_oldest_expires(events: deque[datetime], window_seconds: int, now: datetime) -> int:
    if not events:
        return window_seconds
    expires_at = events[0] + timedelta(seconds=window_seconds)
    return max(1, int((expires_at - now).total_seconds()))


def assert_otp_send_allowed(phone_number: str, client_ip: str) -> None:
    now = datetime.now(timezone.utc)
    forced_rate_limit_phone = settings.OTP_FORCE_RATE_LIMIT_PHONE_NUMBER

    if (
        settings.ENV not in {Environment.PROD.value, Environment.DEV.value}
        and forced_rate_limit_phone and forced_rate_limit_phone.strip()
        
    ):
        phone_number = phone_number.strip().replace("+91", "").strip()
        if phone_number == forced_rate_limit_phone:
            retry_after = settings.OTP_RESEND_COOLDOWN_SECONDS
            log.warning(
                "OTP test rate limit forced for %s",
                mask_phone(phone_number),
            )
            
            raise CabboException(
                "Too many OTP requests for this phone number. Please try again later.",
                status_code=429,
                error_code=OTP_RATE_LIMITED,
                retry_after_seconds=retry_after,
            )

    with _lock:
        phone_events = _phone_events[phone_number]
        ip_events = _ip_events[client_ip]
        daily_events = _phone_daily_events[phone_number]

        _prune(phone_events, now - timedelta(seconds=settings.OTP_PHONE_WINDOW_SECONDS))
        _prune(ip_events, now - timedelta(seconds=settings.OTP_IP_WINDOW_SECONDS))
        _prune(daily_events, now - timedelta(days=1))

        if len(phone_events) >= settings.OTP_PHONE_MAX_SENDS_PER_WINDOW:
            retry_after = _seconds_until_oldest_expires(
                phone_events, settings.OTP_PHONE_WINDOW_SECONDS, now
            )
            log.warning(
                "OTP phone rate limit hit for %s",
                mask_phone(phone_number),
            )
            capture_otp_rate_limit_hit(
                limit_type="phone_window",
                retry_after_seconds=retry_after,
                current_count=len(phone_events),
                configured_limit=settings.OTP_PHONE_MAX_SENDS_PER_WINDOW,
                window_seconds=settings.OTP_PHONE_WINDOW_SECONDS,
            )
            raise CabboException(
                "Too many OTP requests for this phone number. Please try again later.",
                status_code=429,
                error_code=OTP_RATE_LIMITED,
                retry_after_seconds=retry_after,
            )

        if len(ip_events) >= settings.OTP_IP_MAX_SENDS_PER_WINDOW:
            retry_after = _seconds_until_oldest_expires(
                ip_events, settings.OTP_IP_WINDOW_SECONDS, now
            )
            log.warning("OTP IP rate limit hit")
            capture_otp_rate_limit_hit(
                limit_type="ip_window",
                retry_after_seconds=retry_after,
                current_count=len(ip_events),
                configured_limit=settings.OTP_IP_MAX_SENDS_PER_WINDOW,
                window_seconds=settings.OTP_IP_WINDOW_SECONDS,
            )
            raise CabboException(
                "Too many OTP requests. Please try again later.",
                status_code=429,
                error_code=OTP_RATE_LIMITED,
                retry_after_seconds=retry_after,
            )

        if len(daily_events) >= settings.OTP_PHONE_DAILY_CAP:
            retry_after = _seconds_until_oldest_expires(daily_events, 24 * 60 * 60, now)
            log.warning(
                "OTP daily cap hit for %s",
                mask_phone(phone_number),
            )
            capture_otp_rate_limit_hit(
                limit_type="phone_daily",
                retry_after_seconds=retry_after,
                current_count=len(daily_events),
                configured_limit=settings.OTP_PHONE_DAILY_CAP,
                window_seconds=1*24 * 60 * 60,
            )
            raise CabboException(
                "Daily OTP limit reached for this phone number. Please try again tomorrow.",
                status_code=429,
                error_code=OTP_RATE_LIMITED,
                retry_after_seconds=retry_after,
            )


def record_otp_send(phone_number: str, client_ip: str) -> None:
    now = datetime.now(timezone.utc)

    with _lock:
        _phone_events[phone_number].append(now)
        _ip_events[client_ip].append(now)
        _phone_daily_events[phone_number].append(now)
