from datetime import datetime, timedelta, timezone
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import SESSION_CREATION_FAILED, CabboException
from models.customer.customer_orm import CustomerSession
from models.customer.customer_schema import CustomerSessionSchema
from services.auth.session_constants import (
    CUSTOMER_SESSION_LIFETIME,
)

log = logging.getLogger(__name__)


async def create_customer_session(payload: CustomerSessionSchema, db: AsyncSession):
    try:
        if not payload.expires_at:
            now = datetime.now(timezone.utc)
            payload.expires_at = now + CUSTOMER_SESSION_LIFETIME
        db.add(
            CustomerSession(**payload.model_dump(exclude_none=True, exclude_unset=True))
        )  # Use model_dump() to convert Pydantic model to dict
        await db.commit()
        log.info("Session created for customer")
        return True

    except Exception as e:
        await db.rollback()
        log.error(f"Error creating session for customer {payload.customer_id}: {e}")
        raise CabboException(
            message="Failed to create a session for customer",
            error_code=SESSION_CREATION_FAILED,
            status_code=500,
        )


async def revoke_customer_session(
    db: AsyncSession, token_hash: str, now: datetime =datetime.now(timezone.utc)
) -> bool:
    current_customer_session = await get_customer_session(
        db, token_hash=token_hash, now=now
    )
    if not current_customer_session:
        return False
    try:
        current_customer_session.is_active = False
        current_customer_session.revoked_at = now
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        return False


async def get_customer_session(
    db: AsyncSession, token_hash: str, now: datetime | None = None
):
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(CustomerSession).where(
            CustomerSession.token_hash == token_hash,
            CustomerSession.revoked_at.is_(None),  # Not revoked
            CustomerSession.is_active.is_(True),
            CustomerSession.expires_at > now,
        )
    )
    customer_session = result.scalar_one_or_none()
    return customer_session


async def update_customer_session_last_seen(
    db: AsyncSession,
    customer_session: CustomerSession,
    now: datetime = datetime.now(timezone.utc),
    update_threshold_minutes = 15
) -> bool:
    if customer_session.last_seen_at > now - timedelta(minutes=update_threshold_minutes):
        return # Do not update if last seen was updated in the last `update_threshold_minutes` minutes.
    try:
        customer_session.last_seen_at = now
        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        return False

async def get_existing_active_customer_session(customer_id:str, db:AsyncSession, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
            select(CustomerSession).where(
                CustomerSession.customer_id == customer_id,
                CustomerSession.revoked_at.is_(None),  # Not revoked
                CustomerSession.is_active.is_(True),
                CustomerSession.expires_at > now,
            )
        )
    customer_session = result.scalar_one_or_none()
    return customer_session
