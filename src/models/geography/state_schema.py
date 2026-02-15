#Pydantic schema for states/provinces
from typing import List, Optional
from pydantic import BaseModel, Field   
from models.geography.region_schema import RegionSchema

class StateSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the state")  # UUID
    state_name: Optional[str] = Field(None, description="Full name of the state") # e.g. Karnataka
    state_code: Optional[str] = Field(None, description="ISO state code, e.g., 'KA' for Karnataka") # e.g. KA
    country_name: Optional[str] = Field(None, description="Name of the country the state belongs to, e.g., 'India'") # e.g. India
    country_code: Optional[str] = Field(None, description="ISO country code the state belongs to, e.g., 'IN' for India") # e.g. IN
    country_id: Optional[str] = Field(None, description="UUID of the country this state belongs to")  # UUID of the country
    regions: Optional[List[RegionSchema]] = Field(None, description="List of regions within the state") # List of regions
    is_serviceable: Optional[bool] = Field(
        True, description="Indicates if the state is serviceable for operations"
    )

    class Config:
        from_attributes = True
        extra = "allow"

class StateUpdateSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the state")  # UUID
    state_name: Optional[str] = Field(None, description="Full name of the state") # e.g. Karnataka
    state_code: Optional[str] = Field(None, description="ISO state code, e.g., 'KA' for Karnataka") # e.g. KA
    