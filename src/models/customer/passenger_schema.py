from pydantic import BaseModel
from typing import Optional
from datetime import datetime



class PassengerBase(BaseModel):
    name: str
    phone_number: str
    is_active: Optional[bool] = True

    


class PassengerCreate(PassengerBase):
    pass


class PassengerUpdate(PassengerCreate):
    pass


class PassengerOut(PassengerBase):
    id: str
    customer_id: str
    created_at: datetime
    last_modified: datetime

    class Config:
        from_attributes = True


class PassengerRead(BaseModel):
    name: str
    phone_number: str

    class Config:
        from_attributes = True



   

class PassengerRequest(BaseModel):
    id: str
    name: Optional[str] = None
    phone_number: Optional[str] = None

    
    
    class Config:
        from_attributes = True
        exclude_none = True  # Exclude fields with None values from the model dump
