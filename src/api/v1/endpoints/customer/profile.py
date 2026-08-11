from fastapi import (
    APIRouter,
    Cookie,
    Depends,
    Response,
    UploadFile,
    File,
    BackgroundTasks,
)
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import a_yield_mysql_session
from models.common import S3ObjectInfo
from models.customer.customer_orm import Customer
from services.auth.session_constants import CUSTOMER_SESSION_COOKIE_NAME
from services.customer_service import (
    a_get_active_customer_by_id,
    a_transform_to_safe_customer,
    a_update_customer_dob,
    a_update_customer_email,
    a_update_customer_emergency_contact,
    a_update_customer_gender,
    a_update_customer_name,
    a_update_customer_profile,
    a_update_customer_profile_picture,
)
from services.file_service import (
    save_customer_profile_picture,
    remove_customer_profile_picture,
)

from models.customer.customer_schema import (
    CustomerSafeRead,
    CustomerUpdate,
    CustomerReadAfterUpdate,
)
from core.security import RoleEnum, delete_cookie, validate_customer_token
from core.exceptions import (
    LOGOUT_FAILED,
    CabboException,
    USER_NOT_FOUND,
    GENERIC_EXCEPTION,
)
from services.auth.auth_service import revoke_session
from services.validation_service import (
    validate_customer_payload,
)
from services.customer_email_verification_service import send_email_verification
from services.orchestration_service import BackgroundTaskOrchestrator

router = APIRouter()
import logging

log = logging.getLogger(__name__)


# Profile endpoints
# View customer profile, only accessible to the customer themselves for viewing their own profile details. This will validate the JWT token and ensure that the customer can only access their own profile details and not other customers' profiles for privacy and security reasons.
@router.get("/", response_model=CustomerSafeRead)
async def get_customer_profile(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer =  await a_get_active_customer_by_id(current_customer.id, db)
    return await a_transform_to_safe_customer(customer, db)


# Update customer profile, only accessible to the customer themselves for updating their own profile details. This will validate the JWT token and ensure that the customer can only update their own profile details and not other customers' profiles for privacy and security reasons.
@router.put("/update", response_model=CustomerReadAfterUpdate)
async def modify_customer_profile(
    background_tasks: BackgroundTasks,
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer, email_updated = await a_update_customer_profile(current_customer.id, payload, db)
    if email_updated:
        orchestrator = BackgroundTaskOrchestrator(background_tasks)
        orchestrator.add_task(
            send_email_verification,
            task_name="send_email_verification",
            customer_id=str(current_customer.id),
        )
    return customer


# Atomic single updates
@router.patch("/update/email", response_model=dict)
async def modify_customer_email_field(
    background_tasks: BackgroundTasks,
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.email is None:
        raise CabboException(
            "Email field is required.", status_code=400, error_code=GENERIC_EXCEPTION
        )
    updated_email, email_updated = await a_update_customer_email(
        current_customer.id, payload.email, db
    )
    if email_updated:
        orchestrator = BackgroundTaskOrchestrator(background_tasks)
        orchestrator.add_task(
            send_email_verification,
            task_name="send_email_verification",
            customer_id=str(current_customer.id),
        )
        return {
            "email": updated_email,
            "message": "Email updated successfully. Please verify your new email address.",
        }
    return {
        "email": updated_email,
        "message": "Email is the same as the current one. No update needed.",
    }


@router.patch("/update/name", response_model=dict)
async def modify_customer_name_field(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.name is None:
        raise CabboException(
            "Name field is required.", status_code=400, error_code=GENERIC_EXCEPTION
        )
    updated_name = await a_update_customer_name(current_customer.id, payload.name, db)
    return {"name": updated_name, "message": "Name updated successfully."}


@router.patch("/update/dob", response_model=dict)
async def modify_customer_dob_field(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.dob is None:
        raise CabboException(
            "DOB field is required.", status_code=400, error_code=GENERIC_EXCEPTION
        )
    updated_dob = await a_update_customer_dob(current_customer.id, payload.dob, db)
    return {"dob": updated_dob, "message": "Date of Birth updated successfully."}


@router.patch("/update/gender", response_model=dict)
async def modify_customer_gender_field(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.gender is None:
        raise CabboException(
            "Gender field is required.", status_code=400, error_code=GENERIC_EXCEPTION
        )
    updated_gender = await a_update_customer_gender(current_customer.id, payload.gender, db)
    return {"gender": updated_gender, "message": "Gender updated successfully."}


@router.patch("/update/emergency-contact", response_model=dict)
async def modify_customer_emergency_contact(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.emergency_contact_number is None:
        raise CabboException(
            "Emergency contact number is required.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )

    return await a_update_customer_emergency_contact(current_customer.id, payload, db)


@router.post(
    "/upload/profile-picture",
    response_model=S3ObjectInfo,
)
async def upload_profile_picture(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
     
    customer_id = current_customer.id
    customer = await a_get_active_customer_by_id(customer_id, db)
    # Save file and get URL
    new_s3_image_info = save_customer_profile_picture(customer_id, file)
    if new_s3_image_info:
        existing_s3_image_info = (
            S3ObjectInfo.model_validate(customer.s3_image_info)
            if customer.s3_image_info
            else None
        )
        if existing_s3_image_info and existing_s3_image_info.key:
            # Remove old profile picture from S3 silently if it exists, and if new upload is successful
            # We are explictly removing old picture because profile pictures are hex named and we want to avoid orphaned files in S3 which can lead to unnecessary storage costs. By removing old picture immediately after successful upload of new picture, we ensure that there is only one profile picture per customer at any given time, which simplifies management and reduces storage usage. If we don't remove old picture, we would need a separate cleanup process to identify and delete orphaned files, which adds complexity and overhead.
            removed = remove_customer_profile_picture(key=existing_s3_image_info.key)
            if not removed:
                # just log the error but do not raise exception as the new profile picture has been uploaded successfully and we don't want to fail the whole operation just because of failure in removing old picture from S3. This can be handled in a background task for cleanup if needed.
                log.error("Failed to cleanup old profile picture from storage.")
        # finally update customer record with new profile picture info
        _ = await a_update_customer_profile_picture(customer, db, new_s3_image_info)
        return new_s3_image_info
    raise CabboException(
        "Failed to upload profile picture.",
        status_code=500,
        error_code=GENERIC_EXCEPTION,
    )


@router.delete(
    "/remove/profile-picture",
)
async def remove_profile_picture(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
    customer = await a_get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException(
            "Customer not found", status_code=404, error_code=USER_NOT_FOUND
        )
    # Remove file using service
    existing_s3_image_info = (
        S3ObjectInfo.model_validate(customer.s3_image_info)
        if customer.s3_image_info
        else None
    )

    if existing_s3_image_info and existing_s3_image_info.key:
        removed = remove_customer_profile_picture(key=existing_s3_image_info.key)
        if removed:
            # Update customer record to remove profile picture info
            _ = await a_update_customer_profile_picture(customer, db, None)
            return {"message": "Profile picture removed successfully."}
        else:
            raise CabboException(
                "Failed to remove profile picture from storage.",
                status_code=500,
                error_code=GENERIC_EXCEPTION,
            )
    else:
        raise CabboException(
            "No profile picture to remove.",
            status_code=400,
            error_code=GENERIC_EXCEPTION,
        )


@router.get("/is-logged-in")
async def check_logged_in_status(
    _: Customer = Depends(validate_customer_token),
):
    try:
        return True  # If the token is valid and we have a current_customer, it means the user is logged in, so we return True. If the token was invalid or expired, the validate_customer_token dependency would have already raised an exception and this code would not be reached.
    except Exception:
        return False  # If there was any exception (e.g., token validation failed), we catch it and return False, indicating that the user is not logged in. This way, instead of returning an error response, we simply return a boolean indicating the login status.


@router.post("/logout")
async def logout_customer(
    response: Response,
    session_token: str | None = Cookie(
        default=None,
        alias=CUSTOMER_SESSION_COOKIE_NAME,
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    if session_token and await revoke_session(
        session_id=session_token,
        role=RoleEnum.customer,
        db=db,
    ):
        
        delete_cookie(response, key =CUSTOMER_SESSION_COOKIE_NAME )
        return {"message": "Logged out successfully"}

    raise CabboException("Logout failed", status_code=500, error_code=LOGOUT_FAILED)
