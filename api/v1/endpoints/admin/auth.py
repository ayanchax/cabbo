from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.security import JWT_EXPIRY_UNIT, RoleEnum, verify_password_hash
from db.database import get_mysql_session
from models.user.user_schema import UserLoginRequest, UserLoginResponse
from services.user_service import generate_user_jwt, get_user_by_username, is_user_logged_in, persist_bearer_token

router = APIRouter()


# Login as admin user
@router.post("/login", response_model=UserLoginResponse)
def login_admin_user(
    payload: UserLoginRequest = Body(...), db: Session = Depends(get_mysql_session)
):
    """Login as an administrative user."""
    username = payload.username
    password = payload.password
    if not username or not password:
        raise CabboException("Username and password are required.", status_code=400)
    user = get_user_by_username(username=username.strip(), db=db)
    if not user:
        raise CabboException("User not found.", status_code=404)
    if is_user_logged_in(user=user):
        raise CabboException(f"User is already logged in as {user.username}.", status_code=400)
    if not user.password_hash:
        raise CabboException("User does not have a password set.", status_code=400)
    if not user.is_active:
        raise CabboException("User is not active.", status_code=403)
    if not user.role:
        raise CabboException("User role is not defined.", status_code=400)
    if user.role not in [role.value for role in RoleEnum if role.value.endswith("_admin")]:
        raise CabboException("Invalid user role.", status_code=400)

    is_correct_password = verify_password_hash(
        password=password, hashed_password=user.password_hash
    )
    if not is_correct_password:
        raise CabboException("Incorrect password.", status_code=401)
    
    
    
    token = persist_bearer_token(user=user, token=generate_user_jwt(user=user), db=db)
    
    return UserLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRY_UNIT * 24 * 60 * 60,  # n days in seconds
        user_id=str(user.id),
        role=user.role,
    )



