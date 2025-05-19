from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from models.customer.customer_schema import CustomerCreate, CustomerRead
from services.customer_service import create_customer
from db.database import get_mysql_async_session , get_mysql_session  # Make sure this import path is correct

router = APIRouter(prefix="/customers", tags=["customers"])

@router.get("/")
def get_customers():
    return {"message": "List customers endpoint"}

 
