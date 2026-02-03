from fastapi import APIRouter

from models.cab.cab_schema import FuelTypeSchema

router = APIRouter()


# ====== Fuel Configuration Endpoints ================
# Add fuel type
@router.post("/fuel-type", response_model=FuelTypeSchema)
def add_fuel_type(fuel_type: FuelTypeSchema):
    """Add a new fuel type to the system configuration."""
    # Implementation to add fuel type goes here
    return fuel_type


# List fuel types
@router.get("/fuel-types", response_model=list[FuelTypeSchema])
def list_fuel_types():
    """List all fuel types in the system configuration."""
    # Implementation to list fuel types goes here
    return []


# Update fuel type
@router.put("/fuel-type/{fuel_type_id}", response_model=FuelTypeSchema)
def update_fuel_type(fuel_type_id: str, fuel_type: FuelTypeSchema):
    """Update an existing fuel type's configuration."""
    # Implementation to update fuel type goes here
    return fuel_type


# Delete fuel type
@router.delete("/fuel-type/{fuel_type_id}")
def delete_fuel_type(fuel_type_id: str):
    """Delete a fuel type from the system configuration."""
    # Implementation to delete fuel type goes here
    return {"detail": f"Fuel type {fuel_type_id} deleted successfully."}
