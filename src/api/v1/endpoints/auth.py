from fastapi import APIRouter, Depends, BackgroundTasks, Request, Response
from core.security import (
    RoleEnum,
    set_cookie,
)
from db.database import a_yield_mysql_session
from services.auth.auth_service import create_session, get_existing_active_session
from services.auth.session_constants import CUSTOMER_SESSION_COOKIE_NAME, CUSTOMER_SESSION_LIFETIME
from services.customer_service import (
    a_create_customer,
    a_get_customer_by_phone_number,
    a_is_existing_customer,
)
from services.notification_service import notify_customer_onboarded
from services.customer_email_verification_service import send_email_verification
from services.orchestration_service import BackgroundTaskOrchestrator
from services.otp_service import (
    OTP_RESEND_INTERVAL_SECONDS,
    OTPFlow,
    a_delete_otp,
    a_generate_otp,
    a_resend_otp,
    a_verify_otp,
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
from services.message_service import (
    send_otp,
)
from services.otp_rate_limit_service import (
    assert_otp_send_allowed,
    get_client_ip,
    record_otp_send,
)
from core.exceptions import (
    GENERIC_EXCEPTION,
    SESSION_CREATION_FAILED,
    CabboException,
    PHONE_ALREADY_REGISTERED,
    PHONE_NOT_REGISTERED,
    ALREADY_LOGGED_IN,
    OTP_SEND_FAILED,
    INVALID_OTP,
    OTP_RESEND_FAILED,
)
from core.constants import APP_NAME
from services.validation_service import (
    validate_customer_login_payload,
    validate_customer_onboarding_payload,
    validate_customer_payload,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# Onboarding endpoints
@router.post("/onboard/initiate")
async def initiate_onboarding(
    request: Request,
    payload: CustomerOnboardInitiationRequest = Depends(
        validate_customer_onboarding_payload
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    phone_number = payload.phone_number
    # Check if phone number already exists in permanent users
    if await a_is_existing_customer(phone_number, db):
        raise CabboException(
            "Phone number already registered.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )
    client_ip = get_client_ip(request)
    assert_otp_send_allowed(phone_number=phone_number, client_ip=client_ip)
    # Generate OTP and return
    otp, _, _, last_sent_at = await a_generate_otp(phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to complete your registration. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."

    if send_otp(
        to_number=phone_number,
        message=message,
        otp=otp,
        expires_in=str(OTP_EXPIRY_MINUTES),
        flow=OTPFlow.REGISTRATION,
    ):
        record_otp_send(phone_number=phone_number, client_ip=client_ip)
        return {
            "message": "OTP sent to phone number.",
            "phone_number": phone_number,
            "last_sent_at": last_sent_at,
            "resend_interval_seconds": OTP_RESEND_INTERVAL_SECONDS,
        }
    else:
        # If sending OTP fails, delete the OTP record from the database
        await a_delete_otp(phone_number, db)
        raise CabboException(
            "Failed to send OTP. Please try again later.",
            status_code=500,
            error_code=OTP_SEND_FAILED,
        )


@router.post("/onboard/verify")
async def verify_onboarding_otp(
    payload: CustomerOTPRequest = Depends(validate_customer_onboarding_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    phone_number = payload.phone_number
    otp = payload.otp
    # Verify OTP
    valid, message = await a_verify_otp(phone_number, otp, db)
    if not valid:
        raise CabboException(message, status_code=400, error_code=GENERIC_EXCEPTION)
    return {"message": "OTP verified successfully. You can proceed with account setup."}


@router.post("/onboard", response_model=CustomerLoginResponse)
async def onboard_customer(
    request:Request,
    response:Response,
    background_tasks: BackgroundTasks,
    payload: CustomerCreate = Depends(validate_customer_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    phone_number = payload.phone_number
    # Check if already registered
    if await a_is_existing_customer(phone_number, db):
        raise CabboException(
            "Phone number already registered.",
            status_code=400,
            error_code=PHONE_ALREADY_REGISTERED,
        )

    customer = await a_create_customer(data=payload, db=db, phone_verified=True, activate=True)

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
        orchestrator.add_task(
            send_email_verification,
            task_name="send_email_verification",
            customer_id=str(customer.id),
        )

    # Session creation here
    session_token = await create_session(request, customer.id, RoleEnum.customer, db)
    if not session_token:
            raise CabboException(
                "Failed to create session for customer.",
                status_code=500,
                error_code=SESSION_CREATION_FAILED,
            )
    
    #Send cookie from server.
    set_cookie(response=response, key = CUSTOMER_SESSION_COOKIE_NAME, value=session_token, lifetime=CUSTOMER_SESSION_LIFETIME)
    
    return CustomerLoginResponse(
            authenticated=True,
            first_time_login=True
        )


# Onboard endpoints - END


# Authentication endpoints (login, logout, resend OTP)
@router.post("/login/initiate")
async def initiate_login(
    request: Request,
    payload: CustomerOnboardInitiationRequest = Depends(
        validate_customer_login_payload
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    phone_number = payload.phone_number
    customer = await a_get_customer_by_phone_number(phone_number, db)

    if not customer:
        raise CabboException(
            "Phone number not registered.",
            status_code=404,
            error_code=PHONE_NOT_REGISTERED,
        )

    existing_session = await get_existing_active_session(
        entity_id=customer.id,
        role=RoleEnum.customer,
        db=db,
    )
    if existing_session:
        raise CabboException(
            "You are already logged in on another device. Please log out from other devices to continue here.",
            status_code=400,
            error_code=ALREADY_LOGGED_IN,
        )

    client_ip = get_client_ip(request)
    assert_otp_send_allowed(phone_number=phone_number, client_ip=client_ip)
    otp, _, _, last_sent_at = await a_generate_otp(phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to login into your account. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."
    if send_otp(
        to_number=phone_number,
        message=message,
        otp=otp,
        expires_in=str(OTP_EXPIRY_MINUTES),
        flow=OTPFlow.LOGIN,
    ):
        record_otp_send(phone_number=phone_number, client_ip=client_ip)
        return {
            "message": "OTP sent to phone number.",
            "phone_number": phone_number,
            "last_sent_at": last_sent_at,
            "resend_interval_seconds": OTP_RESEND_INTERVAL_SECONDS,
        }
    else:
        await a_delete_otp(phone_number, db)
        raise CabboException(
            "Failed to send OTP. Please try again later.",
            status_code=500,
            error_code=OTP_SEND_FAILED,
        )


@router.post("/login", response_model=CustomerLoginResponse)
async def login(
    request: Request,
    response: Response,
    payload: CustomerLoginRequest = Depends(validate_customer_login_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    phone_number = payload.phone_number
    otp = payload.otp
    # Check if registered and active
    customer = await a_get_customer_by_phone_number(phone_number, db)
    if not customer:
        raise CabboException(
            "Login failed as phone number not registered.",
            status_code=404,
            error_code=PHONE_NOT_REGISTERED,
        )
    # Verify OTP
    valid, message = await a_verify_otp(phone_number, otp, db)
    if not valid:
        raise CabboException(message, status_code=400, error_code=INVALID_OTP)

    # Session creation
    session_token = await create_session(request, customer.id, RoleEnum.customer, db)
    if not session_token:
        raise CabboException(
            "Failed to create session for customer.",
            status_code=500,
            error_code=SESSION_CREATION_FAILED,
        )

    #Send cookie from server.
    set_cookie(response=response, key = CUSTOMER_SESSION_COOKIE_NAME, value=session_token, lifetime=CUSTOMER_SESSION_LIFETIME)
    return CustomerLoginResponse(
        authenticated=True,
    )

@router.post("/resend-otp")
async def resend_one_time_password(
    request: Request,
    payload: CustomerOTPRequest = Depends(validate_customer_onboarding_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    client_ip = get_client_ip(request)
    assert_otp_send_allowed(phone_number=payload.phone_number, client_ip=client_ip)
    otp, _, _, last_sent_at = await a_resend_otp(payload.phone_number, db)
    message = f"Your {APP_NAME} OTP is {otp}. Please use it to complete your registration. This OTP is valid for {str(OTP_EXPIRY_MINUTES)} minutes."

    if send_otp(
        to_number=payload.phone_number,
        message=message,
        otp=otp,
        expires_in=str(OTP_EXPIRY_MINUTES),
        flow=OTPFlow.RESEND,
    ):
        record_otp_send(phone_number=payload.phone_number, client_ip=client_ip)
        return {
            "message": "OTP resent to phone number.",
            "phone_number": payload.phone_number,
            "last_sent_at": last_sent_at,
            "resend_interval_seconds": OTP_RESEND_INTERVAL_SECONDS,
        }
    else:
        # If resending OTP fails, delete the OTP record from the database
        await a_delete_otp(payload.phone_number, db)
        raise CabboException(
            "Failed to resend OTP. Please try again later.",
            status_code=500,
            error_code=OTP_RESEND_FAILED,
        )


# Authentication endpoints - END
