import logging
from fastapi import APIRouter, Depends
from core.exceptions import LOGOUT_FAILED, CabboException
from core.security import validate_user_token
from db.database import yield_mysql_session
from models.user.user_orm import User
from models.user.user_schema import UserReadBaseSchema
from sqlalchemy.orm import Session
from services.user_service import delete_bearer_token, get_user_by_id

router = APIRouter()

log = logging.getLogger(__name__)


@router.get("/", response_model=UserReadBaseSchema)
def get_admin_user(
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get details of an administrative user."""
    user = get_user_by_id(user_id=current_user.id, db=db)
    return UserReadBaseSchema.model_validate(user)


@router.get("/is-logged-in")
def check_logged_in_status(
    _: User = Depends(validate_user_token),
):
    try:
        return True  # If the token is valid and we have a user, it means the user is logged in, so we return True. If the token was invalid or expired, the validate_user_token dependency would have already raised an exception and this code would not be reached.
    except Exception:
        return False  # If there was any exception (e.g., token validation failed), we catch it and return False, indicating that the user is not logged in. This way, instead of returning an error response, we simply return a boolean indicating the login status.


# Logout admin user
@router.post("/logout")
def logout_admin_user(db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Logout an administrative user."""
    if delete_bearer_token(user=current_user, db=db):
        # If the bearer token is deleted successfully, we can assume the logout was successful
        return {"message": "Logged out successfully"}

    raise CabboException("Logout failed", status_code=500, error_code=LOGOUT_FAILED)

