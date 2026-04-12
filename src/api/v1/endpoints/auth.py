from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from core.security import JWT_EXPIRES_IN, validate_customer_token
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from services.customer_service import create_customer, delete_bearer_token
from services.notification_service import notify_customer_onboarded
from services.orchestration_service import BackgroundTaskOrchestrator
from services.otp_service import (
    OTP_RESEND_INTERVAL_SECONDS,
    generate_otp,
    resend_otp,
    verify_otp,
    delete_otp,
    OTP_EXPIRY_MINUTES,
)
from models.customer.customer_schema import (
    CustomerCreate,
    CustomerOTPRequest,
    CustomerOnboardInitiationRequest,
    CustomerLoginRequest,
    CustomerLoginResponse,
    CustomerRead,
)
from services.customer_service import (
    is_existing_customer,
    get_customer_by_phone_number,
    generate_customer_jwt,
    persist_bearer_token,
    is_customer_logged_in,
)
from services.message_service import (
    send_otp,
)
from core.exceptions import CabboException
from core.constants import APP_NAME
from services.validation_service import (
    validate_customer_login_payload,
    validate_customer_onboarding_payload,
    validate_customer_payload,
)

router = APIRouter()


# Onboarding endpoints
@router.post("/onboard/initiate")
def initiate_onboarding(
    payload: CustomerOnboardInitiationRequest = Depends(
        validate_customer_onboarding_payload
    ),
    db: Session = Depends(yield_mysql_session),
):
    phone_number = payload.phone_number
    # Check if phone number already exists in permanent users
    if is_existing_customer(phone_number, db):
        raise CabboException("Phone number already registered.", status_code=400)
    # Generate OTP and return
    otp, _, _, last_sent_at = generate_otp(phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to complete your registration. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."

    if send_otp(to_number=phone_number, message=message):
        return {
            "message": "OTP sent to phone number.",
            "phone_number": phone_number,
            "last_sent_at": last_sent_at,
            "resend_interval_seconds": OTP_RESEND_INTERVAL_SECONDS,
        }
    else:
        # If sending OTP fails, delete the OTP record from the database
        delete_otp(phone_number, db)
        raise CabboException(
            "Failed to send OTP. Please try again later.", status_code=500
        )


@router.post("/onboard/verify")
def verify_onboarding_otp(
    payload: CustomerOTPRequest = Depends(validate_customer_onboarding_payload),
    db: Session = Depends(yield_mysql_session),
):
    phone_number = payload.phone_number
    otp = payload.otp
    # Verify OTP
    valid, message = verify_otp(phone_number, otp, db)
    if not valid:
        raise CabboException(message, status_code=400)
    return {"message": "OTP verified successfully. You can proceed with account setup."}


@router.post("/onboard", response_model=CustomerLoginResponse)
def onboard_customer(
    background_tasks: BackgroundTasks,
    payload: CustomerCreate = Depends(validate_customer_payload),
    db: Session = Depends(yield_mysql_session),
):
    phone_number = payload.phone_number
    # Check if already registered
    if is_existing_customer(phone_number, db):
        raise CabboException("Phone number already registered.", status_code=400, error_code="PHONE_ALREADY_REGISTERED")

    customer = create_customer(data=payload, db=db, phone_verified=True, activate=True)

    if customer.email:
        # If email is provided, send welcome email in background. If email sending fails, it won't block the main flow of registration as it is running in background
        # Send welcome email in background if email is provided
        orchestrator = BackgroundTaskOrchestrator(background_tasks)
        customer_schema = CustomerRead.model_validate(customer)
        orchestrator.add_task(
            notify_customer_onboarded,
            task_name="notify_customer_onboarded",
            customer=customer_schema,
        )

    # Give login token directly after registration
    token = persist_bearer_token(
        customer=customer, token=generate_customer_jwt(customer=customer), db=db
    )
    return CustomerLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRES_IN,  # n days in seconds
        customer_id=str(customer.id),
        first_time_login=True,  # Indicating this is the first login after registration, so that in UI we can show a welcome message or initiate a welcome Tour for customer
    )


# Onboard endpoints - END


# Authentication endpoints (login, logout, resend OTP)
@router.post("/login/initiate")
def initiate_login(
    payload: CustomerOnboardInitiationRequest = Depends(
        validate_customer_login_payload
    ),
    db: Session = Depends(yield_mysql_session),
):
    phone_number = payload.phone_number
    customer = get_customer_by_phone_number(phone_number, db)
    if not customer:
        raise CabboException("Phone number not registered.", status_code=404, error_code="PHONE_NOT_REGISTERED")

    if is_customer_logged_in(customer=customer):
        raise CabboException(
            "Cannot initiate login. You are already logged in.", status_code=400, error_code="ALREADY_LOGGED_IN"
        )

    otp, _, _, last_sent_at = generate_otp(phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to login into your account. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."
    if send_otp(to_number=phone_number, message=message):
        return {
            "message": "OTP sent to phone number.",
            "phone_number": phone_number,
            "last_sent_at": last_sent_at,
            "resend_interval_seconds": OTP_RESEND_INTERVAL_SECONDS,
        }
    else:
        delete_otp(phone_number, db)
        raise CabboException(
            "Failed to send OTP. Please try again later.", status_code=500, error_code="OTP_SEND_FAILED"
        )


@router.post("/login", response_model=CustomerLoginResponse)
def login(
    payload: CustomerLoginRequest = Depends(validate_customer_login_payload),
    db: Session = Depends(yield_mysql_session),
):
    phone_number = payload.phone_number
    otp = payload.otp
    # Check if registered and active
    customer = get_customer_by_phone_number(phone_number, db)
    if not customer:
        raise CabboException(
            "Login failed as phone number not registered.", status_code=404, error_code="PHONE_NOT_REGISTERED"
        )
    # Check if bearer token is still valid in DB
    if is_customer_logged_in(customer=customer):
        raise CabboException("You are already logged in.", status_code=400, error_code="ALREADY_LOGGED_IN")
    # Verify OTP
    valid, message = verify_otp(phone_number, otp, db)
    if not valid:
        raise CabboException(message, status_code=400, error_code="INVALID_OTP")
    token = persist_bearer_token(
        customer=customer, token=generate_customer_jwt(customer=customer), db=db
    )
    return CustomerLoginResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRES_IN,  # n days in seconds
        customer_id=str(customer.id),
    )


@router.post("/customer/logout")
def logout_customer(
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if delete_bearer_token(customer=current_customer, db=db):
        # If the bearer token is deleted successfully, we can assume the logout was successful
        return {"message": "Logged out successfully"}

    raise CabboException("Logout failed", status_code=500, error_code="LOGOUT_FAILED")


@router.post("/resend-otp")
def resend_one_time_password(
    payload: CustomerOTPRequest = Depends(validate_customer_onboarding_payload),
    db: Session = Depends(yield_mysql_session),
):
    customer = get_customer_by_phone_number(
        payload.phone_number, db, silently_fail=True
    )
    if customer and is_customer_logged_in(customer=customer):
        raise CabboException(
            "Failed to resend OTP. You are already logged in.", status_code=400, error_code="ALREADY_LOGGED_IN"
        )

    otp, _, _, last_sent_at = resend_otp(payload.phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to complete your registration. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."

    if send_otp(to_number=payload.phone_number, message=message):
        return {
            "message": "OTP resent to phone number.",
            "phone_number": payload.phone_number,
            "last_sent_at": last_sent_at,
            "resend_interval_seconds": OTP_RESEND_INTERVAL_SECONDS,
        }
    else:
        # If resending OTP fails, delete the OTP record from the database
        delete_otp(payload.phone_number, db)
        raise CabboException(
            "Failed to resend OTP. Please try again later.",
            status_code=500,
            error_code="OTP_RESEND_FAILED",
        )


# Authentication endpoints - END
