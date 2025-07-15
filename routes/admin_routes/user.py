#Route for managing user accounts in the admin panel
from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import get_mysql_session
from models.user.user_orm import User
from models.user.user_schema import UserCreateSchema, UserReadSchema
from services.user_service import create_user, delete_bearer_token

router = APIRouter(prefix="/admin/user", tags=["Admin: User"])

# Create a new admin user
@router.post("/create")
def create_admin_user(payload: UserCreateSchema = Body(...), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Create a new administrative user."""
    
    requested_role = payload.role
    current_user_role = current_user.role

    #If the current user is not a super admin, they can only create users with their own role
    if current_user_role!=RoleEnum.super_admin and requested_role!=current_user_role:
        raise CabboException("You do not have permission to create users with this role.", status_code=403)
    
    #For similar roles or a super admin, allow creation
    if current_user_role==RoleEnum.super_admin or requested_role==current_user_role:
        user = create_user(data=payload, db=db)
        user_schema =UserReadSchema.model_validate(user)
        return user_schema

    raise CabboException("You do not have permission to create users with this role.", status_code=403)

# Get admin user details by id
@router.get("/{user_id}")
def get_admin_user(user_id: str):
    """Get details of an administrative user."""
    return {"message": f"Details for admin user {user_id}"}

# Update admin user
@router.put("/{user_id}")
def update_admin_user(user_id: str):
    """Update an administrative user."""
    return {"message": f"Admin user {user_id} updated"}


# Activate admin user
@router.post("/{user_id}/activate")
def activate_admin_user(user_id: str):
    """Activate an administrative user."""
    return {"message": f"Admin user {user_id} activated"}

# Deactivate admin user
@router.post("/{user_id}/deactivate")
def deactivate_admin_user(user_id: str):
    """Deactivate an administrative user."""
    return {"message": f"Admin user {user_id} deactivated"}

# List all admin users
@router.get("/users")
def list_admin_users():
    """List all administrative users."""
    return {"message": "List of all admin users"}

# List admin users by role
@router.get("/users/role/{role}")
def list_admin_users_by_role(role: str):
    """List all admin users by role."""
    return {"message": f"List of admin users with role {role}"}

# Change password for admin user
@router.post("/{user_id}/change-password")
def change_admin_user_password(user_id: str):
    """Change password for an administrative user."""
    return {"message": f"Password changed for admin user {user_id}"}

#Reset password for admin user
@router.post("/{user_id}/reset-password")
def reset_admin_user_password(user_id: str):
    """Reset password for an administrative user."""
    return {"message": f"Password reset for admin user {user_id}"}

# Logout admin user
@router.post("/logout")
def logout_admin_user(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Logout an administrative user."""
    if delete_bearer_token(user=current_user, db=db):
        # If the bearer token is deleted successfully, we can assume the logout was successful
        return {"message": "Logged out successfully"}

    raise CabboException("Logout failed", status_code=500)



