from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from core.exceptions import CabboException, USER_PASSWORD_NOT_SET, GENERIC_EXCEPTION
from core.security import RoleEnum
from models.user.user_enum import GenderEnum
from core.config import settings

class UserBaseSchema(BaseModel):
    id: Optional[str] =None # Unique identifier for the user

class UserCreateSchema(UserBaseSchema):
    name: Optional[str] = None  # User's name
    username: str  # User's username
    email: Optional[EmailStr] = None  # User's email address
    phone_number: str  # User's phone number
    password: Optional[str]= None  # User's password
    is_active: bool = True  # Active status of the user
    role: RoleEnum #Immutable role for the user
    gender: Optional[GenderEnum] = None  # User's gender Immutable
    dob: Optional[datetime] = None  # Date of birth
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None


    
    @field_validator("password", mode="before")
    @classmethod
    def password_validator(cls, v):
        if not v or len(v) < 8:
            raise CabboException("Password must be at least 8 characters long", status_code=400, error_code=USER_PASSWORD_NOT_SET)
        return v
    
    @field_validator("role", mode="before")
    @classmethod
    def role_validator(cls, v):
        if v not in [role.value for role in RoleEnum if role.value.endswith("_admin")]:
            raise CabboException(
                "Invalid role specified. Allowed roles are: " + ", ".join([role.value for role in RoleEnum if role.value.endswith("_admin")]),
                status_code=400,
                error_code=GENERIC_EXCEPTION,
            )
        return v
    
    class Config:
        exclude_none = True  # Exclude fields with None values from the model dump

class UserUpdateSchema(UserBaseSchema):
    name: Optional[str] = None  # User's name
    username: Optional[str] = None  # User's username
    dob: Optional[datetime] = None  # Date of birth
    email: Optional[EmailStr] = None  # User's email address
    phone_number: Optional[str] = None  # User's phone number
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None

   


class UserPasswordUpdateSchema(UserBaseSchema):
    old_password: str  # Old password for the user      
    password: str  # New password for the user
    confirm_password: str  # Confirm new password
    @field_validator("password", "old_password", mode="before")
    @classmethod
    def password_length_validator(cls, v):
        if not v or len(v) < 8:
            raise CabboException("Password must be at least 8 characters long", status_code=400, error_code=USER_PASSWORD_NOT_SET)
        return v
    # Custom validation to ensure old password is not the same as new password
    @field_validator("password", mode="before")
    @classmethod
    def validate_password(cls, v, info):
        if "old_password" in info.data and v == info.data["old_password"]:
            raise CabboException("New password cannot be the same as old password", status_code=400, error_code=USER_PASSWORD_NOT_SET)
        return v

    @field_validator("confirm_password", mode="before")
    @classmethod
    def validate_confirm_password(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise CabboException("Passwords do not match", status_code=400, error_code=USER_PASSWORD_NOT_SET)
        return v

class UserPasswordResetSchema(UserBaseSchema):
    password: str  # New password for the user

    @field_validator("password", mode="before")
    @classmethod
    def password_length_validator(cls, v):
        if not v or len(v) < 8:
            raise CabboException("Password must be at least 8 characters long", status_code=400, error_code=USER_PASSWORD_NOT_SET)
        return v



class UserReadBaseSchema(BaseModel):
    name: Optional[str] = None  # User's name
    email: Optional[EmailStr] = None  # User's email address
    role: RoleEnum  # User's role

    class Config:
        from_attributes = True
        extra= "allow"

class UserReadSchema(UserReadBaseSchema):
    username: str  # User's username
    phone_number: str  # User's phone number
    is_active: bool  # Active status of the user

    class Config:
        from_attributes = True
        extra= "allow"

class UserLoginRequest(BaseModel):
    username: str   
    password: str  

    @classmethod
    def password_validator(cls, v):
        if not v or len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v 

class UserLoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user_id: str
    first_time_login: Optional[bool] = None
    role: RoleEnum  # User's role for the logged-in user
 

    

