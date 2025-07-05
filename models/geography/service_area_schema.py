# Pydantic schema for API/data validation
from pydantic import BaseModel, Field
from typing import List, Optional

from core.security import RoleEnum


class ServiceableGeographySchema(BaseModel):
    id: Optional[str] = None
    trip_type_id: str
    service_area_name: str
    service_area_code: str
    city_names: Optional[List[str]] = None
    airport_place_ids: Optional[List[str]] = None
    state_codes: Optional[List[str]] = None
    created_by: Optional[RoleEnum] = None
    created_at: Optional[str] = None
    last_modified: Optional[str] = None

    class Config:
        from_attributes = True
