from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from core.security import RoleEnum


class GeoStateBase(BaseModel):
    state_name: str
    state_code: str
    is_home_state: int = 0


class GeoStateCreate(GeoStateBase):
    pass


class GeoStateOut(GeoStateBase):
    id: str
    created_by: RoleEnum
    created_at: Optional[datetime]
    last_modified: Optional[datetime]

    class Config:
        from_attributes = True
