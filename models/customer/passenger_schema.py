from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime

from utils.utility import validate_and_sanitize_country_phone


class PassengerBase(BaseModel):
    name: str
    phone_number: str
    is_active: Optional[bool] = True

    @field_validator("v", mode="before")
    @classmethod
    def phone_validator(cls, v):
        v = v.strip()
        if v == "":
            return v
        return validate_and_sanitize_country_phone(v)


class PassengerCreate(PassengerBase):
    pass


class PassengerOut(PassengerBase):
    id: str
    customer_id: str
    created_at: datetime
    last_modified: datetime

    class Config:
        orm_mode = True
