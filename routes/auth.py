from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from db.database import get_mysql_session
from models.customer.customer_orm import Customer
from services.customer_service import create_customer
from services.otp_service import generate_otp, verify_otp, delete_otp
from models.customer.customer_schema import CustomerCreate, CustomerRead, CustomerOnboardInitiationRequest
from services.customer_service import is_existing_customer
from pydantic import BaseModel

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login")
def login():
    return {"message": "Login endpoint"}

@router.post("/onboard/initiate")
def initiate_onboarding(
    payload: CustomerOnboardInitiationRequest = Body(...),
    db: Session = Depends(get_mysql_session)
):
    phone_number = payload.phone_number
    if not phone_number:
        raise HTTPException(status_code=400, detail="Phone number is required.")
    # Check if phone number already exists in permanent users
    if is_existing_customer(phone_number, db):
        raise HTTPException(status_code=400, detail="Phone number already registered.")
    # Generate OTP and return (in production, send via SMS, here just return for demo)
    otp = generate_otp(phone_number, db)
    return {"message": "OTP sent to phone number.", "phone_number": phone_number, "otp": otp} 



@router.post("/register", response_model=CustomerRead)
def register(
    payload: CustomerCreate = Body(...),
    db: Session = Depends(get_mysql_session)
):
    phone_number = payload.phone_number
    otp = payload.otp
    # Check if already registered
    if is_existing_customer(phone_number, db):
        raise HTTPException(status_code=400, detail="Phone number already registered.")
    # Verify OTP
    valid, message = verify_otp(phone_number, otp, db)
    if not valid:
        raise HTTPException(status_code=400, detail=message)
    
    customer =create_customer(data=payload, db=db)
    
    return customer
