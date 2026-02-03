from fastapi import APIRouter

from models.cab.cab_schema import CabTypeSchema


router = APIRouter()

# ====== Cab Configuration Endpoints ================

# Add cab type 
@router.post("/cab-type", response_model=CabTypeSchema)
def add_cab_type(cab_type: CabTypeSchema):
    """Add a new cab type to the system configuration."""
    # Implementation to add cab type goes here
    return cab_type

# List cab types
@router.get("/cab-types", response_model=list[CabTypeSchema])
def list_cab_types():
    """List all cab types in the system configuration."""
    # Implementation to list cab types goes here
    return []

# Update cab type
@router.put("/cab-type/{cab_type_id}", response_model=CabTypeSchema)
def update_cab_type(cab_type_id: str, cab_type: CabTypeSchema):
    """Update an existing cab type's configuration."""
    # Implementation to update cab type goes here
    return cab_type

# Delete cab type
@router.delete("/cab-type/{cab_type_id}")
def delete_cab_type(cab_type_id: str):
    """Delete a cab type from the system configuration."""
    # Implementation to delete cab type goes here
    return {"detail": f"Cab type {cab_type_id} deleted successfully."}

