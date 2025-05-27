from fastapi import APIRouter, Body, Depends, BackgroundTasks, Header
from sqlalchemy.orm import Session
from db.database import get_mysql_session
from services.customer_service import create_customer
from services.otp_service import (
    generate_otp,
    verify_otp,
    delete_otp,
    OTP_EXPIRY_MINUTES,
)
from models.customer.customer_schema import (
    CustomerCreate,
    CustomerRead,
    CustomerOnboardInitiationRequest,
    CustomerLoginRequest,
    CustomerLoginResponse,
)
from services.customer_service import (
    is_existing_customer,
    get_customer_by_phone_number,
    generate_customer_jwt,
    persist_bearer_token,
    is_customer_logged_in,
)
from services.message_service import send_otp, send_email
from core.exceptions import CabboException
from core.constants import APP_NAME

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/onboard/initiate")
def initiate_onboarding(
    payload: CustomerOnboardInitiationRequest = Body(...),
    db: Session = Depends(get_mysql_session),
):
    phone_number = payload.phone_number
    if not phone_number:
        raise CabboException("Phone number is required.", status_code=400)
    # Check if phone number already exists in permanent users
    if is_existing_customer(phone_number, db):
        raise CabboException("Phone number already registered.", status_code=400)
    # Generate OTP and return (in production, send via SMS, here just return for demo)
    otp = generate_otp(phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to complete your registration. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."

    if send_otp(to_number=phone_number, message=message):
        return {"message": "OTP sent to phone number.", "phone_number": phone_number}
    else:
        # If sending OTP fails, delete the OTP record from the database
        delete_otp(phone_number, db)
        raise CabboException(
            "Failed to send OTP. Please try again later.", status_code=500
        )


@router.post("/register", response_model=CustomerLoginResponse)
def register(
    background_tasks: BackgroundTasks,
    payload: CustomerCreate = Body(...),
    db: Session = Depends(get_mysql_session),
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

    customer = create_customer(data=payload, db=db, phone_verified=True, activate=True)
    # Send welcome email in background if email is provided
    if customer.email and customer.name:
        subject = f"Welcome to {APP_NAME}!"
        html_content = f"<h1>Welcome to {APP_NAME}, {customer.name}!</h1><p>Thank you for registering with us.</p>"
        background_tasks.add_task(send_email, customer.email, subject, html_content)

    # Give login token directly after registration
    token = persist_bearer_token(
        customer=customer, token=generate_customer_jwt(customer=customer), db=db
    )
    return CustomerLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=OTP_EXPIRY_MINUTES * 24 * 60 * 60,
        customer_id=str(customer.id),
        first_time_login=True,  # Indicating this is the first login after registration, so that in UI we can show a welcome message or a welcome Tour
    )


@router.post("/login/initiate")
def initiate_login(
    payload: CustomerOnboardInitiationRequest = Body(...),
    db: Session = Depends(get_mysql_session),
):
    phone_number = payload.phone_number
    if not phone_number:
        raise CabboException("Phone number is required.", status_code=400)
    if not is_existing_customer(phone_number, db):
        raise CabboException("Phone number not registered.", status_code=404)
    otp = generate_otp(phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to login into your account. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."
    if send_otp(to_number=phone_number, message=message):
        return {"message": "OTP sent to phone number.", "phone_number": phone_number}
    else:
        delete_otp(phone_number, db)
        raise CabboException(
            "Failed to send OTP. Please try again later.", status_code=500
        )


@router.post("/login", response_model=CustomerLoginResponse)
def login(
    payload: CustomerLoginRequest = Body(...), db: Session = Depends(get_mysql_session)
):
    phone_number = payload.phone_number
    otp = payload.otp
    # Check if registered and active
    customer = get_customer_by_phone_number(phone_number, db)
    if not customer:
        raise CabboException(
            "Login failed as phone number not registered.", status_code=404
        )
    # Check if bearer token is still valid in DB
    if is_customer_logged_in(customer=customer):
        raise CabboException("You are already logged in.", status_code=400)
    # Verify OTP
    valid, message = verify_otp(phone_number, otp, db)
    if not valid:
        raise CabboException(message, status_code=400)
    token = persist_bearer_token(
        customer=customer, token=generate_customer_jwt(customer=customer), db=db
    )
    return CustomerLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=OTP_EXPIRY_MINUTES * 24 * 60 * 60,
        customer_id=str(customer.id),
    )
