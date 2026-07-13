import jwt
from cabbo_core.constants import APP_NAME
from datetime import datetime, timedelta, timezone
import hmac
import hashlib

JWT_EXPIRY_UNIT = 30
JWT_EXPIRES_IN = JWT_EXPIRY_UNIT * 24 * 60 * 60  # Default expiry in seconds (30 days)
JWT_EXPIRY_UNIT_TIME_FRAME = {
    "DAYS": "days",
    "HOURS": "hours",
    "MINUTES": "minutes",
}


class ActiveInactiveStatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"


class RoleEnum(str, Enum):
    # Admin roles for managing the application
    super_admin = "super_admin"  # Super admin System administrator with full access to all features
    driver_admin = "driver_admin"  # Administrator for driver management such as onboarding, verification etc.
    finance_admin = (
        "fin_admin"  # Administrator for financial operations such as payments etc.
    )
    customer_admin = "cust_admin"  # Administrator for customer management such as deactivation, reactivation etc.
    regional_admin = "regional_admin"  # Regional admin with access to manage operations in specific regions
    state_admin = (
        "state_admin"  # State admin with access to manage operations in specific states
    )

    # Internal roles for seeding or migrations
    system = (
        "system"  # System role for internal operations during seeding or migrations
    )
    # Regular roles
    customer = "customer"  # Regular customer role
    driver = "driver"  # Regular driver role
    support_agent = (
        "support_agent"  # Support agent role for handling customer support queries
    )


def generate_jwt_token(payload, secret: str, algorithm="HS256"):
    """
    Generate a JWT token with a secret key.
    """

    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_jwt_token(token, secret: str, algorithms=["HS256"]):
    """
    Decode a JWT token with a secret key.
    """

    return jwt.decode(token, secret, algorithms=algorithms)


def generate_jwt_payload(
    sub: str,
    identity: str,
    expires_in=JWT_EXPIRY_UNIT,
    expires_unit=JWT_EXPIRY_UNIT_TIME_FRAME.get("DAYS"),
) -> dict:
    now = datetime.now(timezone.utc)
    if expires_unit == JWT_EXPIRY_UNIT_TIME_FRAME.get("DAYS"):
        expire = now + timedelta(days=expires_in)
    elif expires_unit == JWT_EXPIRY_UNIT_TIME_FRAME.get("HOURS"):
        expire = now + timedelta(hours=expires_in)
    elif expires_unit == JWT_EXPIRY_UNIT_TIME_FRAME.get("MINUTES"):
        expire = now + timedelta(minutes=expires_in)
    else:
        expire = now + timedelta(days=JWT_EXPIRY_UNIT)  # fallback
    payload = {
        "iss": APP_NAME,
        "iat": int(now.timestamp()),
        "sub": sub,
        "exp": int(expire.timestamp()),
        "identity": identity,
    }
    return payload


def generate_hash(payload: str, secret_key: str) -> str:
    """
    Generate a hash for the trip booking option and preferences.
    This is used to verify the integrity of the booking data.
    """
    return hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def verify_hash(payload: str, client_hash: str, secret_key: str) -> bool:
    expected_hash = generate_hash(payload, secret_key)
    return hmac.compare_digest(expected_hash, client_hash)


def generate_password_hash(password: str) -> str:
    """
    Generate a secure hash for the password.
    """
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password_hash(password: str, hashed_password: str) -> bool:
    """
    Verify the password against the hashed password.
    """
    return generate_password_hash(password) == hashed_password
