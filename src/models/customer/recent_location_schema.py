from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from models.map.location_schema import LocationInfo


class RecentLocationBase(BaseModel):
    place_id: str
    provider: str
    location: LocationInfo


class RecentLocationCreate(RecentLocationBase):
    customer_id: str


class RecentLocationRead(RecentLocationBase):
    id: str = Field(..., description="UUID v4 recent location ID")
    customer_id: str
    usage_count: int = 1
    last_used_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
        extra="allow"


class RecentLocationUpdate(BaseModel):
    usage_count: Optional[int] = None
    last_used_at: Optional[datetime] = None
    location: Optional[LocationInfo] = None