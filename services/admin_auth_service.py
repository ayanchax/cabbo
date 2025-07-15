from sqlalchemy.orm import Session
from models.user.user_orm import User

def get_user_by_username(username: str,db: Session ):
    """Get user by username."""
    return db.query(User).filter(User.username == username).first()