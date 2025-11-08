from pydantic import BaseModel
from typing import Optional

class CabTypeSchema(BaseModel):
    id: Optional[str]
    name: str
    capacity:Optional[str] = None  # e.g., "4+1", "6+1"

    class Config:
        from_attributes = True


class FuelTypeSchema(BaseModel):
    id: Optional[str]
    name: str

    class Config:
        from_attributes = True