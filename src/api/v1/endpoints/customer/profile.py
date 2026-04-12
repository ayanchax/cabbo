from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session
from db.database import yield_mysql_session
from models.common import S3ObjectInfo
from models.customer.customer_orm import Customer
from services.customer_service import (
    get_active_customer_by_id,
    update_customer_dob,
    update_customer_emergency_contact,
    update_customer_gender,
    update_customer_name,
    update_customer_email,
    update_customer_profile,
    update_customer_profile_picture,
)
from services.file_service import (
    save_customer_profile_picture,
    remove_customer_profile_picture,
)

from models.customer.customer_schema import (
    CustomerRead,
    CustomerUpdate,
    CustomerReadAfterUpdate,
)
from core.security import validate_customer_token
from core.exceptions import CabboException
from services.validation_service import (
    validate_customer_payload,
)
router = APIRouter()

#Profile endpoints
#View customer profile, only accessible to the customer themselves for viewing their own profile details. This will validate the JWT token and ensure that the customer can only access their own profile details and not other customers' profiles for privacy and security reasons.
@router.get("/", response_model=CustomerRead)
def get_customer_profile(
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    return get_active_customer_by_id(current_customer.id, db)


# Update customer profile, only accessible to the customer themselves for updating their own profile details. This will validate the JWT token and ensure that the customer can only update their own profile details and not other customers' profiles for privacy and security reasons.
@router.put("/update", response_model=CustomerReadAfterUpdate)
def modify_customer_profile(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    return update_customer_profile(current_customer.id, payload, db)


#Atomic single updates
@router.patch("/update/email", response_model=dict)
def modify_customer_email_field(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.email is None:
        raise CabboException("Email field is required.", status_code=400)
    updated_email= update_customer_email(current_customer.id, payload.email, db)
    return {"email": updated_email, "message": "Email updated successfully. Please verify your new email address."}

@router.patch("/update/name", response_model=dict)
def modify_customer_name_field(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.name is None:
        raise CabboException("Name field is required.", status_code=400)
    updated_name = update_customer_name(current_customer.id, payload.name, db)
    return {"name": updated_name, "message": "Name updated successfully."}

@router.patch("/update/dob", response_model=dict)
def modify_customer_dob_field(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.dob is None:
        raise CabboException("DOB field is required.", status_code=400)
    updated_dob = update_customer_dob(current_customer.id, payload.dob, db)
    return {"dob": updated_dob, "message": "Date of Birth updated successfully."}

@router.patch("/update/gender", response_model=dict)
def modify_customer_gender_field(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.gender is None:
        raise CabboException("Gender field is required.", status_code=400)
    updated_gender = update_customer_gender(current_customer.id, payload.gender, db)
    return {"gender": updated_gender, "message": "Gender updated successfully."}


@router.patch("/update/emergency-contact", response_model=dict)
def modify_customer_emergency_contact(
    payload: CustomerUpdate = Depends(validate_customer_payload),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if payload.emergency_contact_number is None:
        raise CabboException("Emergency contact number is required.", status_code=400)
    
    return update_customer_emergency_contact(current_customer.id, payload, db)

@router.post(
    "/upload/profile-picture",
    response_model=S3ObjectInfo,
)
def upload_profile_picture(
    file: UploadFile = File(...),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
    customer = get_active_customer_by_id(customer_id, db)
    # Save file and get URL
    new_s3_image_info = save_customer_profile_picture(customer_id, file)
    if new_s3_image_info:
        existing_s3_image_info =S3ObjectInfo.model_validate(customer.s3_image_info) if customer.s3_image_info else None
        if existing_s3_image_info and existing_s3_image_info.key:
            #Remove old profile picture from S3 silently if it exists, and if new upload is successful
            # We are explictly removing old picture because profile pictures are hex named and we want to avoid orphaned files in S3 which can lead to unnecessary storage costs. By removing old picture immediately after successful upload of new picture, we ensure that there is only one profile picture per customer at any given time, which simplifies management and reduces storage usage. If we don't remove old picture, we would need a separate cleanup process to identify and delete orphaned files, which adds complexity and overhead.
            removed = remove_customer_profile_picture(key=existing_s3_image_info.key)
            if not removed:
                #just print the error but do not raise exception as the new profile picture has been uploaded successfully and we don't want to fail the whole operation just because of failure in removing old picture from S3. This can be handled in a background task for cleanup if needed.
                print("Failed to cleanup old profile picture from storage.")
        #finally update customer record with new profile picture info
        _ = update_customer_profile_picture(customer, db, new_s3_image_info)
        return new_s3_image_info
    raise CabboException("Failed to upload profile picture.", status_code=500)
    


@router.delete(
    "/remove/profile-picture",
)
def remove_profile_picture(
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
    customer = get_active_customer_by_id(customer_id, db)
    if customer is None:
        raise CabboException("Customer not found", status_code=404)
    # Remove file using service
    existing_s3_image_info=S3ObjectInfo.model_validate(customer.s3_image_info) if customer.s3_image_info else None
    
    if existing_s3_image_info and existing_s3_image_info.key:
        removed = remove_customer_profile_picture(key=existing_s3_image_info.key)
        if removed:
            # Update customer record to remove profile picture info
            _=update_customer_profile_picture(customer, db, None)
            return {"message": "Profile picture removed successfully."}
        else:
            raise CabboException("Failed to remove profile picture from storage.", status_code=500)
    else:
        raise CabboException("No profile picture to remove.", status_code=400)

@router.get("/is-logged-in")
def check_logged_in_status(
    _: Customer = Depends(validate_customer_token),
):  
    try:
        return True # If the token is valid and we have a current_customer, it means the user is logged in, so we return True. If the token was invalid or expired, the validate_customer_token dependency would have already raised an exception and this code would not be reached.
    except Exception:
        return False # If there was any exception (e.g., token validation failed), we catch it and return False, indicating that the user is not logged in. This way, instead of returning an error response, we simply return a boolean indicating the login status.