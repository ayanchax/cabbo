

from typing import Callable

from pydantic import BaseModel
from datetime import datetime

from models.seed.seed_enum import SeedKeyEnum

class SeedMetadataBase(BaseModel):
    key: SeedKeyEnum
    value: str

class SeedMetadataCreate(SeedMetadataBase):
    pass

class SeedMetadataResponse(SeedMetadataBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SeedRegistryEntry(BaseModel):
    key: SeedKeyEnum
    func: Callable
    depends_on: list[SeedKeyEnum] = []

    class Config:
        arbitrary_types_allowed = True