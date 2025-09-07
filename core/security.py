from fastapi import Depends, Header
from core.exceptions import CabboException
from core.config import settings
import jwt
from models.customer.customer_orm import Customer
from db.database import get_mysql_session
from sqlalchemy.orm import Session
from core.constants import APP_NAME
from datetime import datetime, timedelta, timezone
from enum import Enum
import hmac
import hashlib
import json


JWT_EXPIRY_UNIT = 5
JWT_EXPIRY_UNIT_TIME_FRAME = {
    "DAYS": "days",
    "HOURS": "hours",
    "MINUTES": "minutes",
}
SECRET_KEY = settings.CABBO_TRIP_BOOKING_SECRET_KEY.encode()

 
    

class RoleEnum(str, Enum):
    #Admin roles for managing the application
    super_admin = "super_admin"  # Super admin System administrator with full access to all features
    driver_admin = "driver_admin"  # Administrator for driver management such as onboarding, verification etc.
    finance_admin = "fin_admin"  # Administrator for financial operations such as payments etc.
    customer_admin = "cust_admin"  # Administrator for customer management such as deactivation, reactivation etc.

    #Internal roles for seeding or migrations
    system = (
        "system"  # System role for internal operations during seeding or migrations
    )
    #Regular roles
    customer = "customer"  # Regular customer role
    driver = "driver"  # Regular driver role


def validate_customer_token(
    authorization: str = Header(..., description="Bearer token for authentication"),
    db: Session = Depends(get_mysql_session),
) -> Customer:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise CabboException(
            "Authorization header missing or invalid.", status_code=401
        )
    token = authorization.split(" ", 1)[1]
    print(f"Token: {token}")
    if not token:
        raise CabboException("Token is missing.", status_code=401)
    try:
        payload = decode_jwt_token(token)
        customer_id = payload.get("sub")
        if not customer_id:
            raise CabboException("Invalid token: missing subject.", status_code=401)
        from services.customer_service import get_active_customer_by_id_and_bearer_token

        customer = get_active_customer_by_id_and_bearer_token(customer_id, token, db)
        if not customer:
            raise CabboException("Invalid or expired token.", status_code=401)
        return customer
    except jwt.ExpiredSignatureError:
        raise CabboException("Token has expired.", status_code=401)
    except jwt.InvalidTokenError:
        raise CabboException("Invalid token.", status_code=401)


def validate_user_token(
    authorization: str = Header(..., description="Bearer token for authentication"),
    db: Session = Depends(get_mysql_session),
):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise CabboException(
            "Authorization header missing or invalid.", status_code=401
        )
    token = authorization.split(" ", 1)[1]
    print(f"Token: {token}")
    if not token:
        raise CabboException("Token is missing.", status_code=401)
    try:
        payload = decode_jwt_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise CabboException("Invalid token: missing subject.", status_code=401)
        from services.user_service import get_active_user_by_id_and_bearer_token

        user = get_active_user_by_id_and_bearer_token(user_id, token, db)
        if not user:
            raise CabboException("Invalid or expired token.", status_code=401)
        return user
    except jwt.ExpiredSignatureError:
        raise CabboException("Token has expired.", status_code=401)
    except jwt.InvalidTokenError:
        raise CabboException("Invalid token.", status_code=401)


def generate_jwt_token(payload, secret=settings.JWT_SECRET, algorithm="HS256"):
    """
    Generate a JWT token with a secret key.
    """

    return jwt.encode(payload, secret, algorithm=algorithm)


def decode_jwt_token(token, secret=settings.JWT_SECRET, algorithms=["HS256"]):
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

def generate_trip_hash(option:dict,preferences:dict) -> str:
    """
    Generate a hash for the trip booking option and preferences.
    This is used to verify the integrity of the booking data.
    """
    payload = json.dumps({"option": option, "preferences": preferences}, sort_keys=True)
    return hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()

def verify_trip_hash(option:dict, preferences:dict, client_hash: str) -> bool:
    expected_hash = generate_trip_hash(option, preferences)
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
