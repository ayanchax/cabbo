from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime

class CustomerBase(BaseModel):
    name: str
    email: Optional[EmailStr] = None
    phone_number: str

class UserCreate(CustomerBase):
    pass

class UserRead(CustomerBase):
    id: str = Field(..., description="UUID v4 customer ID")
    created_at: datetime

    class Config: 
        orm_mode = True
