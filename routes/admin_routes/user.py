#Route for managing user accounts in the admin panel
from fastapi import APIRouter, BackgroundTasks, Body, Depends
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token, verify_password_hash
from db.database import get_mysql_session
from models.user.user_orm import User
from models.user.user_schema import UserCreateSchema, UserPasswordResetSchema, UserPasswordUpdateSchema, UserReadSchema, UserUpdateSchema
from services.user_service import activate_user, auto_logoff_user_after_password_change, change_user_password, create_user, deactivate_user, delete_bearer_token, get_all_users, get_user_by_id, get_user_by_username, get_users_by_role, is_user_exists, update_user

router = APIRouter(prefix="/admin/user", tags=["Admin: User"])

# Create a new admin user
@router.post("/create", response_model=UserReadSchema, status_code=201,)
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
        if is_user_exists(user=payload, db=db):
            raise CabboException("User with this username or phone number or email already exists.", status_code=400)
        user = create_user(data=payload, db=db)
        user_schema =UserReadSchema.model_validate(user)
        #Return the created user schema with 201 status code
        return user_schema
    raise CabboException("You do not have permission to create users with this role.", status_code=403)

# Get admin user details by id
@router.get("/{user_id}",response_model=UserReadSchema)
def get_admin_user(user_id: str, db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Get details of an administrative user."""
    current_user_role = current_user.role
    user = get_user_by_id(user_id=user_id, db=db)
     
    if current_user_role==RoleEnum.super_admin or user.role==current_user_role:
        return UserReadSchema.model_validate(user)
    raise CabboException("You do not have permission to view this user.", status_code=403)

# Update admin user
@router.put("/{user_id}")
def update_admin_user(user_id: str, payload: UserUpdateSchema = Body(...), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Update an administrative user."""
    current_user_role = current_user.role
    user = get_user_by_id(user_id=user_id, db=db, active=True) # Ensure the user is active so we can update them
    if current_user_role==RoleEnum.super_admin or user.role==current_user_role or user.id==current_user.id:
        user = update_user(user=user, data=payload, db=db)
        return UserReadSchema.model_validate(user)
    raise CabboException("You do not have permission to update this user.", status_code=403)


# Activate admin user
@router.patch("/{user_id}/activate")
def activate_admin_user(user_id: str, db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Activate an administrative user."""
    current_user_role = current_user.role
    user = get_user_by_id(user_id=user_id, db=db) 
    if current_user_role==RoleEnum.super_admin or user.role==current_user_role:
        if user.is_active:
            raise CabboException("User is already active.", status_code=400)
        _ = activate_user(user=user, db=db)
        return {"message": f"User {user_id} activated"}
    raise CabboException("You do not have permission to activate this user.", status_code=403)

# Deactivate admin user
@router.patch("/{user_id}/deactivate")
def deactivate_admin_user(user_id: str, db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Deactivate an administrative user."""
    current_user_role = current_user.role
    user = get_user_by_id(user_id=user_id, db=db)
    if current_user_role==RoleEnum.super_admin or  user.role==current_user_role:
        
        if user.role==RoleEnum.super_admin and user.id == current_user.id:
            raise CabboException("Super admin user cannot be self deactivated", status_code=403)
        
        if not user.is_active:
            raise CabboException("User is already inactive.", status_code=400)
        _ = deactivate_user(user=user, db=db)

        return {"message": f"User {user_id} deactivated"}
    raise CabboException("You do not have permission to deactivate this user.", status_code=403)

# List all admin users
@router.get("/users/all", response_model=list[UserReadSchema])
def list_admin_users(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """List all administrative users."""
    current_user_role = current_user.role
    if current_user_role != RoleEnum.super_admin:
        raise CabboException("You do not have permission to view all users.", status_code=403)
    users = get_all_users(db=db)
    users = [UserReadSchema.model_validate(user) for user in users]
    return users


# List admin users by role
@router.get("/users/role/{role}")
def list_admin_users_by_role(role: RoleEnum,db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """List all admin users by role."""
    #Role validation to check if role is any of the RoleEnum roles
    if role.value not in [_role.value for _role in RoleEnum if _role.value.endswith("_admin")]:
            raise CabboException(
                "Invalid role specified. Allowed roles are: " + ", ".join([__role.value for __role in RoleEnum]),
                status_code=400
            )
    current_user_role = current_user.role
    if current_user_role != RoleEnum.super_admin and role != current_user_role:
        raise CabboException("You do not have permission to view users with this role.", status_code=403)
    users = get_users_by_role(role=role, db=db)
    users = [UserReadSchema.model_validate(user) for user in users]
    return users

# Change password for admin user
@router.patch("/{user_id}/change-password")
def change_admin_user_password(background_tasks: BackgroundTasks,user_id: str, payload: UserPasswordUpdateSchema, db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Change password for an administrative user."""
    current_user_role = current_user.role
    user = get_user_by_id(user_id=user_id, db=db, active=True)  # Ensure the user is active so we can change their password
    
    if current_user_role == RoleEnum.super_admin or user.id == current_user.id:
        if not verify_password_hash(payload.old_password, user.password_hash):  # Verify old password
            raise CabboException("Old password is incorrect", status_code=400)
        _ = change_user_password(user=user, new_password=payload.password, db=db)
        # Delete the bearer token to force re-authentication
        # after password change
        background_tasks.add_task(auto_logoff_user_after_password_change, user, db)
        return {"message": f"Password changed for admin user {user_id}"}
    
    raise CabboException("You do not have permission to change this user's password.", status_code=403)

# Reset password for admin user
@router.patch("/{user_id}/reset-password")
def reset_admin_user_password(background_tasks: BackgroundTasks,user_id: str, payload: UserPasswordResetSchema, db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Reset password for an administrative user."""
    current_user_role = current_user.role
    user = get_user_by_id(user_id=user_id, db=db, active=True)  # Ensure the user is active so we can reset their password
    if current_user_role == RoleEnum.super_admin or user.id == current_user.id:
        _ = change_user_password(user=user, new_password=payload.password, db=db)
        # Delete the bearer token to force re-authentication
        # after password reset
        background_tasks.add_task(auto_logoff_user_after_password_change, user, db)
        return {"message": f"Password reset for admin user {user_id}"}
    
    raise CabboException("You do not have permission to reset this user's password.", status_code=403)

# Logout admin user
@router.post("/logout")
def logout_admin_user(db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Logout an administrative user."""
    if delete_bearer_token(user=current_user, db=db):
        # If the bearer token is deleted successfully, we can assume the logout was successful
        return {"message": "Logged out successfully"}

    raise CabboException("Logout failed", status_code=500)



