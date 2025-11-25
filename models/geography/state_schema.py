#Pydantic schema for states/provinces
from typing import List, Optional
from pydantic import BaseModel, Field   
from models.geography.country_schema import CountrySchema
from models.geography.region_schema import RegionSchema

class StateSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the state")  # UUID
    state_name: str = Field(..., description="Full name of the state") # e.g. Karnataka
    state_code: str = Field(..., description="ISO state code, e.g., 'KA' for Karnataka") # e.g. KA
    country_code: str = Field(..., description="ISO country code the state belongs to, e.g., 'IN' for India") # e.g. IN
    regions: Optional[List[RegionSchema]] = Field(None, description="List of regions within the state") # List of regions
    enabled: Optional[bool] = Field(
        True, description="Indicates if the state is enabled for operations"
    )

    class Config:
        from_attributes = True
