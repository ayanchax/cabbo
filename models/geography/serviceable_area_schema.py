from typing import List
from pydantic import BaseModel, Field


class ServiceableAreaSchema(BaseModel):
    serviceable_areas: List[str] = Field(
        ...,
        description="List of region or state IDs for the trip type such as [airport_pickup, airport_drop, hourly rental] or [outstation trips]",
    )  # List of region or state IDs for the trip type validated by ServiceableAreaSchema
    trip_type_id: str  # FK to TripType.id
    class Config:
        from_attributes = True
