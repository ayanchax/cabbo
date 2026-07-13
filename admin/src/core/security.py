from fastapi import Depends, Header
from cabbo_core.security import decode_jwt_token
from cabbo_core.exceptions import (
    CabboException,
    TOKEN_MISSING,
    INVALID_TOKEN,
    TOKEN_EXPIRED,
)
from core.config import settings
import jwt
from cabbo_core.db.database import yield_mysql_session
from sqlalchemy.orm import Session

 

import logging
 
log = logging.getLogger(__name__)
 
# System user validation for admin routes, support agent routes etc. This will validate the JWT token and return the user details along with their role and permissions for accessing the admin or support agent routes. We can use this to manage access control for different types of users in the system based on their roles and permissions.
def validate_user_token(
    authorization: str = Header(..., description="Bearer token for authentication"),
    db: Session = Depends(yield_mysql_session),
):
    
    # Query db using async session
    if not authorization or not authorization.lower().startswith("bearer "):
        raise CabboException(
            "Authorization header missing or invalid.", status_code=401, error_code=INVALID_TOKEN
        )
    token = authorization.split(" ", 1)[1]
    if not token:
        raise CabboException("Token is missing.", status_code=401, error_code=TOKEN_MISSING)
    try:
        payload = decode_jwt_token(token, secret=settings.JWT_SECRET)
        user_id = payload.get("sub")
        if not user_id:
            raise CabboException("Invalid token: missing subject.", status_code=401, error_code=INVALID_TOKEN)
        from services.user_service import get_active_user_by_id_and_bearer_token

        user = get_active_user_by_id_and_bearer_token(user_id, token, db)
        if not user:
            raise CabboException("Invalid or expired token.", status_code=401, error_code=INVALID_TOKEN)
        return user
    except jwt.ExpiredSignatureError:
        raise CabboException("Token has expired.", status_code=401, error_code=TOKEN_EXPIRED)
    except jwt.InvalidTokenError:
        raise CabboException("Invalid token.", status_code=401, error_code=INVALID_TOKEN)

 