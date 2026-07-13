from pydantic import BaseModel, Field, computed_field
from typing import Optional, Union

from cabbo_core.security import RoleEnum
from cabbo_core.models.common import LuggageInfoSchema


class CabTypeSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the cab type")
    name: str = Field(
        ..., description="Name of the cab type, e.g., 'sedan', 'suv', 'suv_plus'"
    )
    description: Optional[str] = Field(None, description="Description of the cab type")
    cab_names: Optional[list[str]] = Field(
        None, description="List of cab model names for this cab type"
    )  # e.g., [Dzire, Amaze, Indigo]
    inventory_cab_names: Optional[list[str]] = Field(
        None, description="List of actual inventory cab model names for this cab type"
    )  # e.g., ["Dzire", "Amaze"] - actual cabs in inventory for this type
    capacity: Optional[str] = Field(
        None, description="Capacity of the cab type e.g., '4+1', '6+1'"
    )  # e.g., "4+1", "6+1"
    passenger_capacity: Optional[int] = Field(
        None, description="Number of passengers the cab type can accommodate"
    )  # e.g., 4, 6
    luggage_capacity: Optional[LuggageInfoSchema] = Field(
        None, description="Number of luggage items the cab type can accommodate"
    )  # e.g., 2, 3
    roof_carrier: Optional[bool] = Field(
        default=False, description="Indicates if the cab type has a roof carrier"
    )  # Indicates if the cab type has a roof carrier
    created_by: Optional[str] = Field(
        default=RoleEnum.system.value,
        description="The role of the user who created this cab type",
    )  # RoleEnum value as string, e.g., "system", "admin"
    is_active: Optional[bool] = Field(
        default=True, description="Indicates if the cab type is active or not"
    )

    @computed_field
    @property
    def total_luggages(self) -> int:
        if not self.luggage_capacity:
            return 0
        return (
            (self.luggage_capacity.num_large_suitcases or 0)
            + (self.luggage_capacity.num_carryons or 0)
            + (self.luggage_capacity.num_backpacks or 0)
            + (self.luggage_capacity.num_other_bags or 0)
        )

    class Config:
        from_attributes = True
        extra = "allow"


class CabTypeUpdateSchema(BaseModel):
    id: str = Field(..., description="Unique identifier for the cab type")
    name: Optional[str] = Field(
        None, description="Name of the cab type, e.g., 'sedan', 'suv', 'suv_plus'"
    )
    description: Optional[str] = Field(None, description="Description of the cab type")
    cab_names: Optional[list[str]] = Field(
        None, description="List of cab model names for this cab type"
    )  # e.g., [Dzire, Amaze, Indigo]
    inventory_cab_names: Optional[list[str]] = Field(
        None, description="List of actual inventory cab model names for this cab type"
    )  # e.g., ["Dzire", "Amaze"] - actual cabs in inventory for this type
    capacity: Optional[str] = Field(
        None, description="Capacity of the cab type e.g., '4+1', '6+1'"
    )  # e.g., "4+1", "6+1"
    passenger_capacity: Optional[int] = Field(
        None, description="Number of passengers the cab type can accommodate"
    )  # e.g., 4, 6
    luggage_capacity: Optional[LuggageInfoSchema] = Field(
        None, description="Number of luggage items the cab type can accommodate"
    )  # e.g., 2, 3
    roof_carrier: Optional[bool] = Field(
        default=False, description="Indicates if the cab type has a roof carrier"
    )

    class Config:
        from_attributes = True
        extra = "allow"


class FuelTypeSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the fuel type")
    name: str = Field(
        ..., description="Name of the fuel type, e.g., 'petrol', 'diesel', 'electric'"
    )
    is_active: Optional[bool] = Field(
        default=True, description="Indicates if the fuel type is active or not"
    )

    class Config:
        from_attributes = True
        extra = "allow"


class VehicleCapacitySchema(BaseModel):
    passenger_capacity: Optional[int] = Field(
        None, description="Number of passengers the cab type can accommodate"
    )  # e.g., 4, 6
    luggage_capacity: Optional[Union[LuggageInfoSchema, int]] = Field(
        None, description="Number of luggage items the cab type can accommodate"
    )  # e.g., 2, 3
    capacity_match: Optional[bool] = Field(
        False,
        description="Indicates if the vehicle capacity matches the required capacity for the trip",
    )
    recommended: Optional[bool] = Field(
        False,
        description="Indicates if the vehicle is recommended based on the capacity requirements for the trip",
    )
    rank: Optional[int] = Field(
        None,
        description="Rank of the vehicle based on capacity match and recommendation status",
    )
    roof_carrier: Optional[bool] = Field(
        default=False, description="Indicates if the cab type has a roof carrier"
    )  # Indicates if the cab type has a roof carrier

    class Config:
        from_attributes = True
        extra = "allow"
