from pydantic import BaseModel, Field
from typing import Optional

from core.security import RoleEnum


class CabTypeSchema(BaseModel):
    id: Optional[str]=Field(None, description="Unique identifier for the cab type")
    name: str=Field(..., description="Name of the cab type, e.g., 'sedan', 'suv', 'suv_plus'")
    description: Optional[str] = Field(None, description="Description of the cab type")
    cab_names: Optional[list[str]] = Field(None, description="List of cab model names for this cab type")  # e.g., [Dzire, Amaze, Indigo]  
    inventory_cab_names: Optional[list[str]] = Field(None, description="List of actual inventory cab model names for this cab type")  # e.g., ["Dzire", "Amaze"] - actual cabs in inventory for this type
    capacity:Optional[str] = Field(None, description="Capacity of the cab type e.g., '4+1', '6+1'")  # e.g., "4+1", "6+1"
    created_by: Optional[str] = Field(default=RoleEnum.system.value, description="The role of the user who created this cab type")  # RoleEnum value as string, e.g., "system", "admin"
    is_active: Optional[bool] = Field(default=True, description="Indicates if the cab type is active or not")    

    class Config:
        from_attributes = True
        extra = "allow"

class CabTypeUpdateSchema(BaseModel):
    id: str=Field(..., description="Unique identifier for the cab type")
    name: Optional[str]=Field(None, description="Name of the cab type, e.g., 'sedan', 'suv', 'suv_plus'")
    description: Optional[str] = Field(None, description="Description of the cab type")
    cab_names: Optional[list[str]] = Field(None, description="List of cab model names for this cab type")  # e.g., [Dzire, Amaze, Indigo]  
    inventory_cab_names: Optional[list[str]] = Field(None, description="List of actual inventory cab model names for this cab type")  # e.g., ["Dzire", "Amaze"] - actual cabs in inventory for this type
    capacity:Optional[str] = Field(None, description="Capacity of the cab type e.g., '4+1', '6+1'")  # e.g., "4+1", "6+1"

    class Config:
        from_attributes = True
        extra = "allow"


class FuelTypeSchema(BaseModel):
    id: Optional[str]= Field(None, description="Unique identifier for the fuel type")
    name: str= Field(..., description="Name of the fuel type, e.g., 'petrol', 'diesel', 'electric'")
    is_active: Optional[bool] = Field(default=True, description="Indicates if the fuel type is active or not")
    class Config:
        from_attributes = True
        extra = "allow"

