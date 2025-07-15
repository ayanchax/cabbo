from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr, field_validator
from core.security import RoleEnum
from models.user.user_enum import GenderEnum
from utils.utility import validate_and_sanitize_country_phone

class UserBaseSchema(BaseModel):
    id: str  # Unique identifier for the user

class UserCreateSchema(UserBaseSchema):
    name: Optional[str] = None  # User's name
    username: str  # User's username
    email: Optional[EmailStr] = None  # User's email address
    phone_number: str  # User's phone number
    password: str  # User's password
    role: RoleEnum
    is_active: bool = True  # Active status of the user
    gender: Optional[GenderEnum] = None  # User's gender 
    dob: Optional[datetime] = None  # Date of birth
    emergency_contact_name: Optional[str] = None
    emergency_contact_number: Optional[str] = None


    @field_validator("phone_number","emergency_contact_number", mode="before")
    @classmethod
    def phone_validator(cls, v):
        if v is None:
            return v
        return validate_and_sanitize_country_phone(v)
    
    @field_validator("password", mode="before")
    @classmethod
    def password_validator(cls, v):
        if not v or len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v
    
    class Config:
        exclude_none = True  # Exclude fields with None values from the model dump

class UserUpdateSchema(UserBaseSchema):
    name: Optional[str] = None  # User's name
    username: Optional[str] = None  # User's username
    email: Optional[EmailStr] = None  # User's email address
    phone_number: Optional[str] = None  # User's phone number
    is_active: Optional[bool] = None  # Active status of the user


class UserPasswordUpdateSchema(UserBaseSchema):
    password: str  # New password for the user
    @field_validator("password", mode="before")
    @classmethod
    def password_validator(cls, v):
        if not v or len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v
    
class UserReadSchema(UserBaseSchema):
    name: Optional[str] = None  # User's name
    username: str  # User's username
    email: Optional[EmailStr] = None  # User's email address
    phone_number: str  # User's phone number
    role: RoleEnum  # User's role
    is_active: bool  # Active status of the user

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
 

    

