from fastapi import APIRouter, Depends
from core.exceptions import UNAUTHORIZED, CabboException
from core.security import RoleEnum, validate_user_token
from core.store import ConfigStore
from db.database import  yield_mysql_session
from models.user.user_orm import User
from sqlalchemy.orm import Session

router = APIRouter()


@router.post("/reset-db-cache")
async def reset_db_cache(
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Reset the database cache. This endpoint can be triggered by admin after changing any configuration in database, so that the cache picks it up immediately and there is almost zero downtime."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to reset the database cache.",
            status_code=403,
            error_code=UNAUTHORIZED,
        )
    # This could involve clearing cached data, resetting in-memory structures, etc.
    ConfigStore.reset_instance(
        db, force_reload=True
    )  # Reset the config store instance to refresh the cache

    return {"message": "Database cache has been reset."}
