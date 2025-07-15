
from operator import or_
from core.exceptions import CabboException
from core.security import JWT_EXPIRY_UNIT, JWT_EXPIRY_UNIT_TIME_FRAME, RoleEnum, decode_jwt_token, generate_jwt_payload, generate_jwt_token, generate_password_hash
from models.user.user_orm import User
from sqlalchemy.orm import Session

from models.user.user_schema import UserCreateSchema, UserPasswordUpdateSchema, UserUpdateSchema


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
    
    if not user:
        raise CabboException("User not found or inactive.", status_code=404)
    
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

def get_user_by_id(user_id: str, db: Session) -> User:
    """Get user by ID."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise CabboException("User not found.", status_code=404)
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
    """Check if user exists in the database by username or (non-null) email."""
    query = db.query(User).filter(User.username == user.username, User.phone_number == user.phone_number)
    if user.email:
        query = query.union(db.query(User).filter(User.email == user.email))
    existing_user = query.first()
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
    if data.name is not None:
        user.name = data.name
    if data.email is not None:
        user.email = data.email
    if data.phone_number is not None:
        user.phone_number = data.phone_number
    
    db.commit()
    db.refresh(user)
    return user

def change_user_password(user: User, new_password: UserPasswordUpdateSchema, db: Session) -> User:
    """Change user password."""
    user.password_hash = generate_password_hash(new_password.password)
    db.commit()
    db.refresh(user)
    return user

def create_user(data:UserCreateSchema, db: Session) -> User:
    """Create a new user."""
    user = User(
        name=data.name or "",  # Default to empty string if name is None
        username=data.username,
        email=data.email,
        phone_number=data.phone_number,
        password_hash=generate_password_hash(data.password) if data.password else None,  # Assuming password is hashed before passing
        role=data.role,
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
