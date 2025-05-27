from fastapi import (
    APIRouter,
    Depends,
    Path,
    Body,
    BackgroundTasks,
    Query,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session
from db.database import get_mysql_session
from models.customer.customer_orm import Customer
from services.customer_service import (
    get_active_customer_by_id,
    update_customer_profile,
    delete_bearer_token,
    mark_customer_email_verified,
    is_customer_email_verified,
    update_customer_last_modified,
)
from services.customer_email_verification_service import (
    is_email_verification_link_already_sent,
    create_customer_email_verification,
    is_email_verification_link_valid,
    remove_email_verification,
    SELF_SERVICE_CUSTOMER_EMAIL_VERIFICATION_ENDPOINT,
)
from services.file_service import (
    save_customer_profile_picture,
    remove_customer_profile_picture,
)

from models.customer.customer_schema import (
    CustomerReadWithProfilePicture,
    CustomerUpdate,
    CustomerReadAfterUpdate,
    CustomerReadProfilePictureAfterUpdate,
)
from core.security import validate_customer_token
from core.exceptions import CabboException
from services.message_service import send_email, EMAIL_VERIFY_EXPIRY_UNIT
from core.constants import APP_NAME

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/")
def get_customers():
    return {"message": "List customers endpoint"}


@router.get("/{customer_id}", response_model=CustomerReadWithProfilePicture)
def get_customer_profile(
    customer_id: str = Path(..., description="UUID of the customer"),
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if str(current_customer.id) != customer_id:
        raise CabboException("Unauthorized", status_code=403)
    return get_active_customer_by_id(customer_id, db)


@router.put("/{customer_id}", response_model=CustomerReadAfterUpdate)
def modify_customer_profile(
    customer_id: str,
    payload: CustomerUpdate = Body(...),
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if str(current_customer.id) != customer_id:
        raise CabboException("Unauthorized", status_code=403)
    return update_customer_profile(customer_id, payload, db)


@router.post(
    "/{customer_id}/upload/profile-picture",
    response_model=CustomerReadProfilePictureAfterUpdate,
)
def upload_profile_picture(
    customer_id: str = Path(..., description="UUID of the customer"),
    file: UploadFile = File(...),
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    # Only allow self-service
    if str(current_customer.id) != customer_id:
        raise CabboException("Unauthorized", status_code=403)
    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        # Do not upload picture if customer does not exist
        raise CabboException("Customer not found", status_code=404)
    # Save file and get URL
    image_url = save_customer_profile_picture(customer_id, file)
    updated_customer = update_customer_last_modified(customer, db)
    return CustomerReadProfilePictureAfterUpdate(
        image_url=image_url, last_modified=updated_customer.last_modified
    )


@router.delete(
    "/{customer_id}/remove/profile-picture",
)
def remove_profile_picture(
    customer_id: str = Path(..., description="UUID of the customer"),
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    # Only allow self-service
    if str(current_customer.id) != customer_id:
        raise CabboException("Unauthorized", status_code=403)
    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException("Customer not found", status_code=404)
    # Remove file using service
    removed = remove_customer_profile_picture(customer_id)
    if not removed:
        # Do not update last modified if no picture was removed
        raise CabboException("No profile picture found to remove.", status_code=404)
    update_customer_last_modified(customer_id, db)
    return {"message": "Profile picture removed successfully."}


@router.post("/logout")
def logout_customer(
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if delete_bearer_token(customer=current_customer, db=db):
        # If the bearer token is deleted successfully, we can assume the logout was successful
        return {"message": "Logged out successfully"}

    raise CabboException("Logout failed", status_code=500)


@router.post("/{customer_id}/self-service/initiate-email-verification")
def trigger_email_verification(
    background_tasks: BackgroundTasks,
    customer_id: str = Path(..., description="UUID of the customer"),
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    # Only allow self-service
    if str(current_customer.id) != customer_id:
        raise CabboException("Unauthorized", status_code=403)
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

    # Send email in background
    subject = f"Verify your email for {customer.name or APP_NAME}"
    html_content = f"<p>Click <a href='{customer_email_verification.verification_url}'>here</a> to verify your email. This link expires in {str(EMAIL_VERIFY_EXPIRY_UNIT)} hours.</p>"
    background_tasks.add_task(send_email, customer.email, subject, html_content)
    return {"message": "Verification email sent. Please check your inbox."}


@router.get(SELF_SERVICE_CUSTOMER_EMAIL_VERIFICATION_ENDPOINT)
def verify_email(
    id: str = Query(..., description="Customer UUID"),
    token: str = Query(..., description="Verification token"),
    db: Session = Depends(get_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
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
