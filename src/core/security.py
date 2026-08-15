from __future__ import annotations

import secrets

from fastapi import Cookie, Depends, Request, Response
from core.exceptions import (
    UNAUTHORIZED,
    CabboException,
)
from db.database import a_yield_mysql_session
from datetime import timedelta
from enum import Enum
import hmac
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession

from typing import TYPE_CHECKING

from services.auth.session_constants import (
    CUSTOMER_SESSION_COOKIE_NAME,
    SYSTEM_USER_SESSION_COOKIE_NAME,
)

if TYPE_CHECKING:
    from models.customer.customer_orm import Customer
    from models.user.user_orm import User

import logging

log = logging.getLogger(__name__)


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


async def validate_customer_token(
    request: Request,
    session_token: str | None = Cookie(
        default=None,
        alias=CUSTOMER_SESSION_COOKIE_NAME,
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
) -> Customer:
    unauthorized = CabboException(
        "Unauthorized.", status_code=401, error_code=UNAUTHORIZED
    )

    if not session_token:
        raise unauthorized

    from services.auth.auth_service import get_session, update_session_last_seen

    # Get the hashed token from the opaque token
    customer_session = await get_session(
        session_id=session_token, role=RoleEnum.customer, db=db
    )

    if customer_session is None:
        raise unauthorized

    from models.customer.customer_orm import Customer

    customer = await db.get(Customer, customer_session.customer_id)

    if customer is None or not customer.is_active or customer.is_suspended:
        raise unauthorized
    await update_session_last_seen(session=customer_session, db=db)
    request.state.customer_session = customer_session

    return customer


async def validate_user_token(
    request: Request,
    session_token: str | None = Cookie(
        default=None,
        alias=SYSTEM_USER_SESSION_COOKIE_NAME,
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
) -> User:
    unauthorized = CabboException(
        "Unauthorized.", status_code=401, error_code=UNAUTHORIZED
    )

    if not session_token:
        raise unauthorized

    from services.auth.auth_service import get_session, update_session_last_seen

    # Get the hashed token from the opaque token
    system_user_session = await get_session(
        session_id=session_token, role=RoleEnum.system, db=db
    )

    if system_user_session is None:
        raise unauthorized

    from models.user.user_orm import User

    system_user = await db.get(User, system_user_session.user_id)

    if system_user is None or not system_user.is_active:
        raise unauthorized
    await update_session_last_seen(session=system_user_session, db=db)
    request.state.system_user_session = system_user_session

    return system_user


def generate_simple_hash(s:str):
    return hashlib.sha256(s.encode()).hexdigest()

def generate_hash(payload: str, secret:bytes) -> str:
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()

def verify_hash(payload: str, client_hash: str, secret:bytes) -> bool:
    expected_hash = generate_hash(payload, secret=secret)
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

def generate_session_token() -> str:
    # 32 random bytes = 256 bits of entropy/unavailable to guess.
    return secrets.token_urlsafe(32)

def hash_session_token(token: str) -> str:
    """
    Hash a 256 bits random session token in hexadecimal.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def set_cookie(response: Response, key: str, value: str, lifetime: timedelta):
    response.set_cookie(
        key=key,
        value=value,
        max_age=int(lifetime.total_seconds()),
        path="/",
        secure=True,  # Cookie should only be sent over HTTPS connections to prevent eavesdropping and man-in-the
        httponly=True,
        samesite="lax",  # Set to "lax" to allow the cookie to be sent with top-level navigations and GET requests initiated by third-party websites. This is a balance between security and usability, allowing the session cookie to be sent in most cases while still providing some protection against CSRF attacks.
    )

def delete_cookie(response: Response, key: str):
    response.delete_cookie(
        key=key,
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )
