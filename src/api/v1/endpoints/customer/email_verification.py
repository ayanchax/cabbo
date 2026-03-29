
from fastapi import (
    APIRouter,
    Depends,
    BackgroundTasks,
    Query,
)
from sqlalchemy.orm import Session
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from services.customer_service import (
    get_active_customer_by_id,
    mark_customer_email_verified,
    is_customer_email_verified,
)
from services.customer_email_verification_service import (
    is_email_verification_link_already_sent,
    create_customer_email_verification,
    is_email_verification_link_valid,
    remove_email_verification,
)

from models.customer.customer_schema import (
    CustomerRead,
)
from core.security import validate_customer_token
from core.exceptions import CabboException
from services.notification_service import notify_verification_email_to_customer
from services.orchestration_service import BackgroundTaskOrchestrator
router = APIRouter()


@router.post("/initiate")
def trigger_email_verification(
    background_tasks: BackgroundTasks,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
    if is_customer_email_verified(customer_id, db):
        return {"message": "Email already verified."}
    customer = get_active_customer_by_id(customer_id, db)
    # Check for existing, unexpired verification link
    if is_email_verification_link_already_sent(customer.id, db):
        return {
            "message": "A verification link has already been sent. Please check your email."
        }
    customer_email_verification = create_customer_email_verification(customer.id, db)
    if not customer_email_verification:
        raise CabboException(
            "Failed to create email verification link", status_code=500
        )

    customer_schema = CustomerRead.model_validate(customer)
    orchestrator = BackgroundTaskOrchestrator(background_tasks)
    orchestrator.add_task(
        notify_verification_email_to_customer,
        task_name="notify_verification_email_to_customer",
        customer=customer_schema,
        verification_url=customer_email_verification.verification_url,
    )
    return {"message": "Verification email sent. Please check your inbox."}


@router.get("/verify")
def verify_email(
    id: str = Query(..., description="Customer UUID"),
    token: str = Query(..., description="Verification token"),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Verify customer's email using the provided id and token passed in the query parameters of the verification link.
    This endpoint will be called when the customer clicks on the verification link sent to their email.
    The customer has to be logged in to verify their email and they can only verify their own email for security reasons, 
    hence the JWT token validation and check to ensure the customer can only verify their own email.
    """
    # Only allow self-service
    if str(current_customer.id) != id:
        raise CabboException("Unauthorized", status_code=403)

    if is_customer_email_verified(id, db):
        return {"message": "Email already verified."}

    valid_email_verification = is_email_verification_link_valid(id, token, db)
    if not valid_email_verification:
        raise CabboException("Invalid or expired verification link.", status_code=400)

    # Mark email as verified
    if mark_customer_email_verified(valid_email_verification.customer_id, db):
        if remove_email_verification(
            email_verification=valid_email_verification, db=db
        ):
            return {"message": "Email verified successfully."}
    raise CabboException("Failed to verify email", status_code=500)
