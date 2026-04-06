from fastapi import Depends, Header
from core.exceptions import CabboException
from core.config import settings
import jwt
from db.database import yield_mysql_session
from sqlalchemy.orm import Session
from core.constants import APP_NAME, Environment
from datetime import datetime, timedelta, timezone
from enum import Enum
import hmac
import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.customer.customer_orm import Customer


JWT_EXPIRY_UNIT = 5
JWT_EXPIRY_UNIT_TIME_FRAME = {
    "DAYS": "days",
    "HOURS": "hours",
    "MINUTES": "minutes",
}
SECRET_KEY = settings.CABBO_TRIP_BOOKING_SECRET_KEY.encode()

 


class ActiveInactiveStatusEnum(str, Enum):
    active = "active"
    inactive = "inactive"
    
    

class RoleEnum(str, Enum):
    #Admin roles for managing the application
    super_admin = "super_admin"  # Super admin System administrator with full access to all features
    driver_admin = "driver_admin"  # Administrator for driver management such as onboarding, verification etc.
    finance_admin = "fin_admin"  # Administrator for financial operations such as payments etc.
    customer_admin = "cust_admin"  # Administrator for customer management such as deactivation, reactivation etc.
    regional_admin = "regional_admin"  # Regional admin with access to manage operations in specific regions
    state_admin = "state_admin"  # State admin with access to manage operations in specific states
    
    #Internal roles for seeding or migrations
    system = (
        "system"  # System role for internal operations during seeding or migrations
    )
    #Regular roles
    customer = "customer"  # Regular customer role
    driver = "driver"  # Regular driver role
    support_agent = "support_agent"  # Support agent role for handling customer support queries

#Customer validation for customer routes, this will validate the JWT token and return the customer details for accessing the customer routes. We can use this to manage access control for different types of users in the system based on their roles and permissions.
def validate_customer_token(
    authorization: str = Header(..., description="Bearer token for authentication"),
    db: Session = Depends(yield_mysql_session),
) -> "Customer":
    
    if not authorization or not authorization.lower().startswith("bearer "):
        raise CabboException(
            "Authorization header missing or invalid.", status_code=401
        )
    token = authorization.split(" ", 1)[1]
    if settings.ENV == Environment.DEV.value:
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


# System user validation for admin routes, support agent routes etc. This will validate the JWT token and return the user details along with their role and permissions for accessing the admin or support agent routes. We can use this to manage access control for different types of users in the system based on their roles and permissions.
def validate_user_token(
    authorization: str = Header(..., description="Bearer token for authentication"),
    db: Session = Depends(yield_mysql_session),
):
    
    # Query db using async session
    

    if not authorization or not authorization.lower().startswith("bearer "):
        raise CabboException(
            "Authorization header missing or invalid.", status_code=401
        )
    token = authorization.split(" ", 1)[1]
    if settings.ENV == Environment.DEV.value:
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


#Note: 
# When we release driver app(when app scales and we get investment), we can have a separate validation function for driver token which will validate the JWT token and return the driver details along with their role and permissions for accessing the driver routes. 
# This will use the the Driver orm table to validate the driver token and return the driver details. 
# This will help us to keep the actors of the system viz., system user, customer and driver authentication separate and manage them independently based on their specific requirements and access controls. We can also have separate JWT secret keys for customer and driver tokens for added security.

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

def generate_hash(payload:str) -> str:
    """
    Generate a hash for the trip booking option and preferences.
    This is used to verify the integrity of the booking data.
    """
    return hmac.new(SECRET_KEY, payload.encode(), hashlib.sha256).hexdigest()

def verify_hash(payload:str, client_hash: str) -> bool:
    expected_hash = generate_hash(payload)
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
