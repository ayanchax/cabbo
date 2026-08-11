import logging
from fastapi import APIRouter, Cookie, Depends, Response
from core.exceptions import LOGOUT_FAILED, CabboException
from core.security import RoleEnum, delete_cookie, validate_user_token
from db.database import a_yield_mysql_session
from models.user.user_orm import User
from models.user.user_schema import UserReadBaseSchema
from services.auth.auth_service import revoke_session
from services.auth.system_user_session_service import SYSTEM_USER_SESSION_COOKIE_NAME
from services.user_service import a_get_user_by_id
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

log = logging.getLogger(__name__)


@router.get("/", response_model=UserReadBaseSchema)
async def get_admin_user(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get details of an administrative user."""
    user = await a_get_user_by_id(user_id=current_user.id, db=db)
    return UserReadBaseSchema.model_validate(user)


@router.get("/is-logged-in")
async def check_logged_in_status(
    _: User = Depends(validate_user_token),
):
    try:
        return True  # If the token is valid and we have a user, it means the user is logged in, so we return True. If the token was invalid or expired, the validate_user_token dependency would have already raised an exception and this code would not be reached.
    except Exception:
        return False  # If there was any exception (e.g., token validation failed), we catch it and return False, indicating that the user is not logged in. This way, instead of returning an error response, we simply return a boolean indicating the login status.


# Logout admin user
@router.post("/logout")
async def logout_admin_user(
    response: Response,
    session_token: str | None = Cookie(
        default=None,
        alias=SYSTEM_USER_SESSION_COOKIE_NAME,
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: User = Depends(validate_user_token),
):
    """Logout an administrative user."""
    if session_token and await revoke_session(
        session_id=session_token,
        role=RoleEnum.system,
        db=db,
    ):
        delete_cookie(response, key=SYSTEM_USER_SESSION_COOKIE_NAME)
        return {"message": "Logged out successfully"}
    raise CabboException("Logout failed", status_code=500, error_code=LOGOUT_FAILED)
