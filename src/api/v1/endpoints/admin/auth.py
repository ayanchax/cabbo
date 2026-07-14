from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from core.exceptions import ALREADY_LOGGED_IN, CREDENTIALS_NOT_PROVIDED, GENERIC_EXCEPTION, INCORRECT_PASSWORD, ROLE_ERROR, USER_INACTIVE, USER_NOT_FOUND, USER_PASSWORD_NOT_SET, CabboException
from core.security import ADMIN_JWT_EXPIRES_IN, JWT_EXPIRY_UNIT, RoleEnum, verify_password_hash
from db.database import yield_mysql_session
from models.user.user_schema import UserLoginRequest, UserLoginResponse
from services.user_service import generate_user_jwt, get_user_by_username, is_user_logged_in, persist_bearer_token

router = APIRouter()


# Login as admin user
@router.post("/login", response_model=UserLoginResponse)
def login_admin_user(
    payload: UserLoginRequest = Body(...), db: Session = Depends(yield_mysql_session)
):
    """Login as an administrative user."""
    username = payload.username
    password = payload.password
    if not username or not password:
        raise CabboException("Username and password are required.", status_code=400, error_code=CREDENTIALS_NOT_PROVIDED)
    user = get_user_by_username(username=username.strip(), db=db)
    if not user:
        raise CabboException("User not found.", status_code=404, error_code=USER_NOT_FOUND)
    if not user.is_active:
        raise CabboException("User is not active.", status_code=403, error_code=USER_INACTIVE)
    if is_user_logged_in(user=user):
        raise CabboException(f"User is already logged in as {user.username}.", status_code=400, error_code=ALREADY_LOGGED_IN)
    if not user.password_hash:
        raise CabboException("User does not have a password set.", status_code=400, error_code=USER_PASSWORD_NOT_SET)
    
    if not user.role:
        raise CabboException("User role is not defined.", status_code=400, error_code=ROLE_ERROR)
    if user.role not in [role.value for role in RoleEnum if role.value.endswith("_admin")]:
        raise CabboException("Invalid user role.", status_code=400, error_code=ROLE_ERROR)

    is_correct_password = verify_password_hash(
        password=password, hashed_password=user.password_hash
    )
    if not is_correct_password:
        raise CabboException("Incorrect password.", status_code=401, error_code = INCORRECT_PASSWORD)
    
    
    
    token = persist_bearer_token(user=user, token=generate_user_jwt(user=user), db=db)
    
    return UserLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=ADMIN_JWT_EXPIRES_IN,  # n days in seconds
        user_id=str(user.id),
        role=user.role,
    )



