from datetime import datetime, timedelta, timezone
import logging
from sqlalchemy import case, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from core.exceptions import SESSION_CREATION_FAILED, CabboException
from db.database import AsyncSessionLocal
from models.user.user_orm import SystemUserSession
from models.user.user_schema import SystemUserSessionSchema
from services.auth.session_constants import (
    SYSTEM_USER_SESSION_LIFETIME,
)
from utils.utility import as_utc_datetime

log = logging.getLogger(__name__)


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
    db: AsyncSession, token_hash: str, now: datetime | None = None
) -> bool:
    now = now or datetime.now(timezone.utc)
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
    now: datetime | None = None,
    update_threshold_minutes=30,
) -> bool:
    now = as_utc_datetime(now or datetime.now(timezone.utc))
    last_seen_at = as_utc_datetime(user_session.last_seen_at)
    if last_seen_at > now - timedelta(minutes=update_threshold_minutes):
        return # Do not update if last seen was updated in the last `update_threshold_minutes` minutes.
    try:
        user_session.last_seen_at = now
        await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        return False

async def get_existing_active_system_user_session(
    user_id: str, db: AsyncSession, now: datetime | None = None
):
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


async def get_existing_expired_sessions(
    user_id: str, db: AsyncSession, now: datetime | None = None
):
    now = now or datetime.now(timezone.utc)
    result = await db.execute(
        select(SystemUserSession).where(
            SystemUserSession.user_id == user_id,
            SystemUserSession.expires_at < now,
            or_(
                SystemUserSession.revoked_at.is_(None),
                SystemUserSession.is_active.is_(True),
            ),
        )
    )
    return result.scalars().all()


async def revoke_expired_system_user_sessions(
    user_id: str,
    db: AsyncSession,
    now: datetime | None = None,
) -> int:
    now = now or datetime.now(timezone.utc)
    try:
        result = await db.execute(
            update(SystemUserSession)
            .where(
                SystemUserSession.user_id == user_id,
                SystemUserSession.expires_at < now,
                or_(
                    SystemUserSession.revoked_at.is_(None),
                    SystemUserSession.is_active.is_(True),
                ),
            )
            .values(
                is_active=False,
                revoked_at=case(
                    (SystemUserSession.revoked_at.is_(None), now),
                    else_=SystemUserSession.revoked_at,
                ),
            )
        )
        await db.commit()
        revoked_count = result.rowcount or 0
        log.info(
            "Revoked expired system user sessions",
            extra={"user_id": user_id, "revoked_count": revoked_count},
        )
        return revoked_count
    except Exception as e:
        await db.rollback()
        log.error(
            f"Failed to revoke expired system user sessions for user {user_id}: {e}"
        )
        return 0


async def revoke_expired_system_user_sessions_in_background(user_id: str) -> None:
    async with AsyncSessionLocal() as db:
        await revoke_expired_system_user_sessions(user_id=user_id, db=db)
