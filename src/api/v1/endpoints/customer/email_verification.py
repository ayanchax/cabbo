from fastapi import (
    APIRouter,
    Depends,
    BackgroundTasks,
    Query,
)
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from services.customer_service import (
    a_get_active_customer_by_id,
    a_is_customer_email_verified,
    a_mark_customer_email_verified,
)
from services.customer_email_verification_service import (
    a_create_customer_email_verification,
    a_get_existing_email_verification_link,
    a_is_email_verification_link_valid,
    a_remove_email_verification,
)

from models.customer.customer_schema import (
    CustomerRead,
)
from core.security import validate_customer_token
from core.exceptions import (
    EMAIL_ALREADY_VERIFIED,
    EMAIL_VERIFICATION_CREATION_FAILED,
    EMAIL_VERIFICATION_FAILED,
    INVALID_VERIFICATION_LINK,
    NO_EMAIL_FOUND,
    CabboException,
)
from services.notification_service import notify_verification_email_to_customer
from services.orchestration_service import BackgroundTaskOrchestrator

router = APIRouter()


@router.post("/initiate")
async def trigger_email_verification(
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
    if await a_is_customer_email_verified(customer_id, db):
        return {"message": "Email already verified."}
    customer = await a_get_active_customer_by_id(customer_id, db)
    if customer and not customer.email:
        raise CabboException(
            "Cannot send verification email. No email address found for the customer.",
            status_code=400,
            error_code=NO_EMAIL_FOUND,
        )
    verification_link = None
    # Check for existing, unexpired verification link
    existing_email_verification = await a_get_existing_email_verification_link(customer.id, db)
    if existing_email_verification:
        verification_link = existing_email_verification.verification_url
    else:
        customer_email_verification = await a_create_customer_email_verification(
            customer.id, db
        )
        if not customer_email_verification:
            raise CabboException(
                "Failed to create email verification link",
                status_code=500,
                error_code=EMAIL_VERIFICATION_CREATION_FAILED,
            )
        verification_link = (
            customer_email_verification.verification_url
            if customer_email_verification
            else None
        )

    if not verification_link:
        raise CabboException(
            "Failed to create email verification link",
            status_code=500,
            error_code=EMAIL_VERIFICATION_CREATION_FAILED,
        )
    if existing_email_verification:
        # Skip sending email if an existing verification link is found and is still valid
        return {"message": "Verification email already sent. Please check your inbox."}
    orchestrator = BackgroundTaskOrchestrator(background_tasks)
    orchestrator.add_task(
        notify_verification_email_to_customer,
        task_name="notify_verification_email_to_customer",
        customer=CustomerRead.model_validate(customer),
        verification_url=verification_link,
    )
    return {"message": "Verification email sent. Please check your inbox."}


@router.get("/verify")
async def verify_email(
    id: str = Query(..., description="Customer UUID"),
    token: str = Query(..., description="Verification token"),
    db: AsyncSession = Depends(a_yield_mysql_session),
):
    """
    Verify customer's email using the provided id and token passed in the query parameters of the verification link.
    This endpoint will be called when the customer clicks on the verification link sent to their email.
    The verification link is treated as proof of access to the customer's email inbox, so the customer
    does not need to be logged in when opening the link from a different browser or device.
    """

    customer = await a_get_active_customer_by_id(id, db)

    if customer.is_email_verified:
        raise CabboException(
            "Email already verified.",
            status_code=400,
            error_code=EMAIL_ALREADY_VERIFIED,
        )

    valid_email_verification = await a_is_email_verification_link_valid(id, token, db)
    if not valid_email_verification:
        raise CabboException(
            "Invalid or expired verification link.",
            status_code=400,
            error_code=INVALID_VERIFICATION_LINK,
        )

    # Mark email as verified
    if await a_mark_customer_email_verified(valid_email_verification.customer_id, db):
        if await a_remove_email_verification(
            email_verification=valid_email_verification, db=db
        ):
            return {"message": "Email verified successfully."}
    raise CabboException(
        "Failed to verify email", status_code=500, error_code=EMAIL_VERIFICATION_FAILED
    )
