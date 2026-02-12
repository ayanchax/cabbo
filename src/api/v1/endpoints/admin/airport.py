# - Airport endpoints for adding, listing, updating and deleting airports in a region, can be 
# operated only by super admin

from fastapi import APIRouter


router = APIRouter()

@router.post("/add")
async def add_airport():
    """Add a new airport to the system configuration."""
    pass

@router.get("/list")
async def list_airports():
    """List all airports in the system configuration."""
    pass

@router.put("/{airport_id}")
async def update_airport(airport_id: str):
    """Update an existing airport's configuration."""
    pass

@router.delete("/{airport_id}")
async def delete_airport(airport_id: str):
    """Delete an airport from the system configuration."""
    pass