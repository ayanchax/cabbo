from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.exceptions import SESSION_CREATION_FAILED, CabboException
from models.user.user_orm import SystemUserSession
from models.user.user_schema import SystemUserSessionSchema

log = logging.getLogger(__name__)

SYSTEM_USER_SESSION_COOKIE_NAME = "__Host-cabbo_sysuser_session"
SYSTEM_USER_SESSION_LIFETIME = timedelta(
    days=1
)  # Absolute expiry at 1 days for SYSTEM users.


async def create_system_user_session(payload: SystemUserSessionSchema, db: AsyncSession):
    try:
        if not payload.expires_at:
            now = datetime.now(timezone.utc)
            payload.expires_at = now + SYSTEM_USER_SESSION_LIFETIME
        db.add(
            SystemUserSession(**payload.model_dump(exclude_none=True, exclude_unset=True))
        )  # Use model_dump() to convert Pydantic model to dict
        await db.commit()
        log.info("Session created for system user")
        return True

    except Exception as e:
        await db.rollback()
        log.error(f"Error creating session for system user {payload.user_id}: {e}")
        raise CabboException(
            message="Failed to create a session for system user",
            error_code=SESSION_CREATION_FAILED,
            status_code=500,
        )


async def revoke_system_user_session(
    db: AsyncSession, token_hash: str, now: datetime =datetime.now(timezone.utc)
) -> bool:
    current_user_session = await get_system_user_session(
        db, token_hash=token_hash, now=now
    )
    if not current_user_session:
        return False
    try:
        current_user_session.is_active = False
        current_user_session.revoked_at = now
        await db.commit()
        return True
    except Exception:
        await db.rollback()
        return False


async def get_system_user_session(
    db: AsyncSession, token_hash: str, now: datetime | None = None
):
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(SystemUserSession).where(
            SystemUserSession.token_hash == token_hash,
            SystemUserSession.revoked_at.is_(None),  # Not revoked
            SystemUserSession.is_active.is_(True),
            SystemUserSession.expires_at > now,
        )
    )
    user_session = result.scalar_one_or_none()
    return user_session


async def update_system_user_session_last_seen(
    db: AsyncSession,
    user_session: SystemUserSession,
    now: datetime = datetime.now(timezone.utc),
    update_threshold_minutes = 30
) -> bool:
    if user_session.last_seen_at > now - timedelta(minutes=update_threshold_minutes):
        return # Do not update if last seen was updated in the last `update_threshold_minutes` minutes.
    try:
        user_session.last_seen_at = now
        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        return False

async def get_existing_active_system_user_session(user_id:str, db:AsyncSession, now: datetime | None = None):
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
            select(SystemUserSession).where(
                SystemUserSession.user_id == user_id,
                SystemUserSession.revoked_at.is_(None),  # Not revoked
                SystemUserSession.is_active.is_(True),
                SystemUserSession.expires_at > now,
            )
        )
    user_session = result.scalar_one_or_none()
    return user_session
