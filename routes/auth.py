from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session
from db.database import get_mysql_session
from services.customer_service import create_customer
from services.otp_service import generate_otp, verify_otp,delete_otp
from models.customer.customer_schema import CustomerCreate, CustomerRead, CustomerOnboardInitiationRequest
from services.customer_service import is_existing_customer
from services.message_service import send_otp
from core.exceptions import CabboException

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
        raise CabboException("Phone number is required.", status_code=400)
    # Check if phone number already exists in permanent users
    if is_existing_customer(phone_number, db):
        raise CabboException("Phone number already registered.", status_code=400)
    # Generate OTP and return (in production, send via SMS, here just return for demo)
    otp = generate_otp(phone_number, db)
    if send_otp(to_number=phone_number, otp=otp):
        return {"message": "OTP sent to phone number.", "phone_number": phone_number} 
    else:
        # If sending OTP fails, delete the OTP record from the database
        delete_otp(phone_number, db)
        raise CabboException("Failed to send OTP. Please try again later.", status_code=500)

@router.post("/register", response_model=CustomerRead)
def register(
    payload: CustomerCreate = Body(...),
    db: Session = Depends(get_mysql_session)
):
    phone_number = payload.phone_number
    otp = payload.otp
    # Check if already registered
    if is_existing_customer(phone_number, db):
        raise CabboException("Phone number already registered.", status_code=400)
    # Verify OTP
    valid, message = verify_otp(phone_number, otp, db)
    if not valid:
        raise CabboException(message, status_code=400)
    
    customer =create_customer(data=payload, db=db, phone_verified=True, activate=True)
    #Onboarding done
    # Here you can add any additional background steps needed after successful registration, e.g. sending a welcome email if email is available.
    
    return customer
