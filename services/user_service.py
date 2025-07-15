
from core.exceptions import CabboException
from core.security import JWT_EXPIRY_UNIT, JWT_EXPIRY_UNIT_TIME_FRAME, generate_jwt_payload, generate_jwt_token
from models.user.user_orm import User
from sqlalchemy.orm import Session


def persist_bearer_token(user: User, token: str, db: Session) -> str:
    try:
        user.bearer_token = token
        db.commit()
        db.refresh(user)
        return token
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error persisting bearer token: {str(e)}",
            status_code=500,
            include_traceback=True,
        )

def generate_user_jwt(
    user: User,
    expires_in=JWT_EXPIRY_UNIT,
    expires_unit=JWT_EXPIRY_UNIT_TIME_FRAME.get("DAYS"),
) -> str:
    payload = generate_jwt_payload(
        sub=str(user.id),
        identity=user.phone_number,
        expires_in=expires_in,
        expires_unit=expires_unit,
    )
    return generate_jwt_token(payload)

