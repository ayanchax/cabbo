
import sys
from pathlib import Path
parent_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(parent_dir))
from sqlalchemy import or_
from core.constants import SUPER_ADMIN
from core.exceptions import CabboException
from core.security import JWT_EXPIRY_UNIT, JWT_EXPIRY_UNIT_TIME_FRAME, RoleEnum, decode_jwt_token, generate_jwt_payload, generate_jwt_token, generate_password_hash
from models.user.user_orm import User
from sqlalchemy.orm import Session
from core.config import settings

from models.user.user_schema import UserCreateSchema, UserUpdateSchema
import logging

logger = logging.getLogger(__name__)

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

def get_active_user_by_id_and_bearer_token(
    user_id: str, token: str, db: Session
) -> User:
    """
    Get an active user by ID and bearer token.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.bearer_token == token,
        User.is_active.is_(True),
    ).first()
    
     
    return user

def delete_bearer_token(user: User, db: Session) -> bool:
    try:
        user.bearer_token = None
        db.commit()
        db.refresh(user)
        return True
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error deleting bearer token: {str(e)}",
            status_code=500,
            include_traceback=True,
        )
    
def get_user_by_username(username: str,db: Session ):
    """Get user by username."""
    return db.query(User).filter(User.username == username).first()

def get_user_by_id(user_id: str, db: Session, active: bool = False) -> User:
    """Get user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise CabboException("User not found.", status_code=404)
    if active and not user.is_active:
        raise CabboException("User is inactive.", status_code=404)
    return user

def get_user_by_email(email: str, db: Session) -> User:
    """Get user by email."""
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise CabboException("User not found.", status_code=404)
    return user

def get_user_by_phone_number(phone_number: str, db: Session) -> User:
    """Get user by phone number."""
    user = db.query(User).filter(User.phone_number == phone_number).first()
    if not user:
        raise CabboException("User not found.", status_code=404)
    return user

def get_user_password_hash_by_username(username: str) -> str:
    """Get user password by username."""
    user = get_user_by_username(username=username)
    if not user or not user.password_hash:
        raise CabboException("User not found or password not set.", status_code=404)
    
    return user.password_hash

def is_user_exists(user: UserCreateSchema, db: Session) -> bool:
    """Check if user exists in the database by username, phone number, or (non-null) email."""
    filters = [
        User.username == user.username,
        User.phone_number == user.phone_number
    ]
    if user.email:
        filters.append(User.email == user.email)
    existing_user = db.query(User).filter(or_(*filters)).first()
    return existing_user is not None
   
def activate_user(user: User, db: Session) -> User:
    """Activate a user."""
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user

def deactivate_user(user: User, db: Session) -> User:
    """Deactivate a user."""
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user

def get_all_users(db: Session) -> list[User]:
    """Get all users."""
    users = db.query(User).all()
    if not users:
        raise CabboException("No users found.", status_code=404)
    return users

def get_all_active_users(db: Session) -> list[User]:
    """Get all active users."""
    users = db.query(User).filter(User.is_active.is_(True)).all()
    if not users:
        raise CabboException("No active users found.", status_code=404)
    return users

def get_all_inactive_users(db: Session) -> list[User]:
    """Get all inactive users."""
    users = db.query(User).filter(User.is_active.is_(False)).all()
    if not users:
        raise CabboException("No inactive users found.", status_code=404)
    return users

def get_all_users(db: Session) -> list[User]:
    """Get all users."""
    users = db.query(User).all()
    if not users:
        raise CabboException("No users found.", status_code=404)
    return users

def get_users_by_role(role: RoleEnum, db: Session) -> list[User]:
    """Get users by role."""
    users = db.query(User).filter(User.role == role).all()
    if not users:
        raise CabboException(f"No users found with role {role}.", status_code=404)
    return users

def update_user(user: User, data: UserUpdateSchema, db: Session) -> User:
    """Update user details."""
    try:
        print(user.username)
        print(data.username)
        if data.name is not None:
            if user.name != data.name:
                user.name = data.name.strip()
        if data.username is not None:
            if user.username != data.username:
                existing_user = db.query(User).filter(
                    User.username == data.username.strip(),
                    User.id != user.id
                ).first()
                if existing_user:
                    raise CabboException("Username already exists.", status_code=400)
                user.username = data.username.strip()

        if data.email is not None:
            if user.email != data.email:
                existing_user = db.query(User).filter(
                    User.email == data.email.strip(),
                    User.id != user.id
                ).first()
                if existing_user:
                    raise CabboException("Email already exists.", status_code=400)
                user.email = data.email.strip()

        if data.phone_number is not None:
            if user.phone_number != data.phone_number:
                existing_user = db.query(User).filter(
                    User.phone_number == data.phone_number.strip(),
                    User.id != user.id
                ).first()
                if existing_user:
                    raise CabboException("Phone number already exists.", status_code=400)
                user.phone_number = data.phone_number.strip()

        db.commit()
        db.refresh(user)
        return user
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error updating user: {str(e)}",
            status_code=500,
            include_traceback=True,
        )
    

def change_user_password(user: User, new_password: str, db: Session) -> User:
    """Change user password."""
    user.password_hash = generate_password_hash(new_password)
    db.commit()
    db.refresh(user)
    return user

def create_user(data:UserCreateSchema, db: Session) -> User:
    """Create a new user."""
    user = User(
        name=data.name.strip() or "",  # Default to empty string if name is None
        username=data.username.strip(),
        email=data.email.strip() if data.email else None,  # Default to None if email is not provided
        phone_number=data.phone_number.strip(),
        password_hash=generate_password_hash(data.password) if data.password else settings.CABBO_USER_DEFAULT_PASSWORD,  # Assuming password is hashed before passing
        role=data.role.strip(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def is_user_logged_in(user: User) -> bool:
    if not user.bearer_token:
        return False
    try:
        decode_jwt_token(
            user.bearer_token
        )  # Decode the JWT token and raise error if invalid or expired
        return True
    except Exception:
        return False

def auto_logoff_user_after_password_change(user: User, db: Session) -> bool:
    """
    Automatically log off the user by deleting their bearer token after password change.
    """
    try:
        if user.bearer_token:
            delete_bearer_token(user=user, db=db)
        return True
    except Exception as e:
        logger.error(f"Error logging off user after password change: {str(e)}")

def create_super_admin_user(db:Session):
    super_admin = User(
        **SUPER_ADMIN,
        password_hash=settings.CABBO_SUPER_ADMIN_SECRET,
        is_active=True,
    )
    db.add(super_admin)
    db.flush()  # Flush to assign an ID to the super admin
         
# if __name__ == "__main__":
#     secret = generate_password_hash("P@55w0rd1234")
#     print(secret)