from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone_number: str

class UserCreate(UserBase):
    pass

class UserRead(UserBase):
    id: str = Field(..., description="UUID v4 user ID")
    created_at: datetime

    class Config: 
        orm_mode = True
