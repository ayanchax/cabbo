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



