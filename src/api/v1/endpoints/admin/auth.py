from fastapi import APIRouter, BackgroundTasks, Body, Depends, Request, Response
from core.exceptions import (
    ALREADY_LOGGED_IN,
    CREDENTIALS_NOT_PROVIDED,
    INCORRECT_PASSWORD,
    ROLE_ERROR,
    SESSION_CREATION_FAILED,
    USER_INACTIVE,
    USER_NOT_FOUND,
    USER_PASSWORD_NOT_SET,
    CabboException,
)
from core.security import (
    RoleEnum,
    set_cookie,
    verify_password_hash,
)
from db.database import a_yield_mysql_session
from models.user.user_schema import (
    UserLoginRequest,
    UserLoginResponse,
)
from services.auth.auth_service import (
    create_session,
    get_existing_active_session,
    revoke_expired_sessions_in_background,
)

from services.auth.session_constants import (
    SYSTEM_USER_SESSION_COOKIE_NAME,
    SYSTEM_USER_SESSION_LIFETIME,
)
from services.orchestration_service import BackgroundTaskOrchestrator
from services.user_service import (
    a_get_user_by_username,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# Login as admin user
@router.post("/login", response_model=UserLoginResponse)
async def login_admin_user(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    payload: UserLoginRequest = Body(...),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    """Login as an administrative user."""
    username = payload.username
    password = payload.password
    if not username or not password:
        raise CabboException(
            "Username and password are required.",
            status_code=400,
            error_code=CREDENTIALS_NOT_PROVIDED,
        )
    user = await a_get_user_by_username(username=username.strip(), db=db)
    if not user:
        raise CabboException(
            "User not found.", status_code=404, error_code=USER_NOT_FOUND
        )
    if not user.is_active:
        raise CabboException(
            "User is not active.", status_code=403, error_code=USER_INACTIVE
        )
    if not user.role:
        raise CabboException(
            "User role is not defined.", status_code=400, error_code=ROLE_ERROR
        )
    if user.role not in [
        role.value for role in RoleEnum if role.value.endswith("_admin")
    ]:
        raise CabboException(
            "Invalid user role.", status_code=400, error_code=ROLE_ERROR
        )
    if not user.password_hash:
        raise CabboException(
            "User does not have a password set.",
            status_code=400,
            error_code=USER_PASSWORD_NOT_SET,
        )

    if await get_existing_active_session(entity_id=user.id,role=RoleEnum.system,db=db):
        raise CabboException(
            f"User is already logged in as {user.username} on another device. Please log out from other devices to continue here.",
            status_code=400,
            error_code=ALREADY_LOGGED_IN,
        )

    is_correct_password = verify_password_hash(
        password=password, hashed_password=user.password_hash
    )
    if not is_correct_password:
        raise CabboException(
            "Incorrect password.", status_code=401, error_code=INCORRECT_PASSWORD
        )

    # Create session

    session_token = await create_session(request, user.id, RoleEnum.system, db)
    if not session_token:
        raise CabboException(
            "Failed to create session for user.",
            status_code=500,
            error_code=SESSION_CREATION_FAILED,
        )

    # Send cookie from server.
    set_cookie(
        response=response,
        key=SYSTEM_USER_SESSION_COOKIE_NAME,
        value=session_token,
        lifetime=SYSTEM_USER_SESSION_LIFETIME,
    )

    orchestrator = BackgroundTaskOrchestrator(background_tasks)
    orchestrator.add_task(
        revoke_expired_sessions_in_background,
        task_name="revoke_expired_system_user_sessions",
        entity_id=str(user.id),
        role=RoleEnum.system,
    )

    return UserLoginResponse(authenticated=True)
