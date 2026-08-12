from datetime import datetime, timezone
from typing import Union

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from core.security import (
    RoleEnum,
    generate_session_token,
    hash_session_token,
)
from models.customer.customer_orm import CustomerSession
from models.user.user_orm import SystemUserSession
from services.auth.customer_session_service import (
    create_customer_session,
    get_customer_session,
    get_existing_active_customer_session,
    revoke_customer_session,
    update_customer_session_last_seen,
)
from services.auth.system_user_session_service import create_system_user_session, get_existing_active_system_user_session, get_system_user_session, revoke_system_user_session
from services.otp_rate_limit_service import get_client_ip


async def create_session(
    request: Request, entity_id: str, role: RoleEnum, db: AsyncSession
):
    now = datetime.now(timezone.utc)
    raw_token = (
        generate_session_token()
    )  # Opaque token generated for the session. This is not a JWT token. It is a random string that is stored in the database and used to identify the session.
    session_created = False
    if role == RoleEnum.customer:
        from models.customer.customer_schema import CustomerSessionSchema
        customer_session = CustomerSessionSchema(
            customer_id=entity_id,
            token_hash=hash_session_token(raw_token),
            last_seen_at=now,
            user_agent=request.headers.get("user-agent"),
            ip_address=get_client_ip(request),
        )
        session_created = await create_customer_session(customer_session, db)
    elif role == RoleEnum.system:
        from models.user.user_schema import SystemUserSessionSchema
        user_session = SystemUserSessionSchema(
            user_id=entity_id,
            token_hash=hash_session_token(raw_token),
            last_seen_at=now,
            user_agent=request.headers.get("user-agent"),
            ip_address=get_client_ip(request),
        )
        session_created = await create_system_user_session(user_session, db)
    if session_created:
        return raw_token  # opaque token
    return None

     

async def get_session(session_id: str, role: RoleEnum, db: AsyncSession):
    token_hash = hash_session_token(session_id)
    if role == RoleEnum.customer:
        return await get_customer_session(db=db, token_hash=token_hash)

    if role == RoleEnum.system:  # System user
        return await get_system_user_session(db=db, token_hash=token_hash)


async def get_existing_active_session(entity_id: str, role: RoleEnum, db: AsyncSession):
    if role == RoleEnum.customer:
        return await get_existing_active_customer_session(customer_id=entity_id, db=db)
    if role == RoleEnum.system:
        return await get_existing_active_system_user_session(user_id=entity_id, db=db)



async def update_session_last_seen(
    session: Union[CustomerSession, SystemUserSession], db: AsyncSession
):
    if isinstance(session, CustomerSession):
        return await update_customer_session_last_seen(db=db, customer_session=session)

    if isinstance(session, SystemUserSession):
        pass


async def revoke_session(session_id: str, role: RoleEnum, db: AsyncSession):
    token_hash = hash_session_token(session_id)
    if role == RoleEnum.customer:
        return await revoke_customer_session(db=db, token_hash=token_hash)

    if role == RoleEnum.system:  # System user
        return await revoke_system_user_session(db=db, token_hash=token_hash)
    return False
