from fastapi import APIRouter, Depends, Path, Body
from sqlalchemy.orm import Session
from db.database import get_mysql_session
from services.customer_service import get_active_customer_by_id, update_customer_profile
from models.customer.customer_schema import CustomerReadWithProfilePicture, CustomerUpdate, CustomerReadAfterUpdate
from core.security import cabbo_auth
router = APIRouter(prefix="/customers", tags=["customers"])

@router.get("/")
def get_customers():
    return {"message": "List customers endpoint"}

@router.get("/{customer_id}", response_model=CustomerReadWithProfilePicture)
def get_customer_profile(
    customer_id: str = Path(..., description="UUID of the customer"),
    db: Session = Depends(get_mysql_session),
    cabbo_auth=Depends(cabbo_auth)
):
    return get_active_customer_by_id(customer_id, db)

@router.put("/{customer_id}", response_model=CustomerReadAfterUpdate)
def update_customer_profile_route(
    customer_id: str,
    payload: CustomerUpdate = Body(...),
    db: Session = Depends(get_mysql_session),
    cabbo_auth=Depends(cabbo_auth)
):
    return update_customer_profile(customer_id, payload, db)




