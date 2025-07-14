from fastapi import APIRouter

router = APIRouter(prefix="/admin/driver", tags=["Admin: Driver"])

@router.get("/drivers")
def list_drivers():
    """List all drivers (placeholder)."""
    return {"message": "List of drivers (admin view)"}

@router.post("/drivers/assign")
def assign_driver():
    """Assign a driver to a trip (placeholder)."""
    return {"message": "Driver assigned to trip (admin action)"}
