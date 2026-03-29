from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from services.customer_service import (
    get_active_customer_by_id,
    update_customer_profile,
    delete_bearer_token,
    update_customer_last_modified,
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
from services.validation_service import (
    validate_customer_payload,
)
router = APIRouter()

#Profile endpoints
#View customer profile, only accessible to the customer themselves for viewing their own profile details. This will validate the JWT token and ensure that the customer can only access their own profile details and not other customers' profiles for privacy and security reasons.
@router.get("/", response_model=CustomerReadWithProfilePicture)
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
    response_model=CustomerReadProfilePictureAfterUpdate,
)
def upload_profile_picture(
    file: UploadFile = File(...),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    customer_id = current_customer.id
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
    removed = remove_customer_profile_picture(customer_id)
    if not removed:
        # Do not update last modified if no picture was removed
        raise CabboException("No profile picture found to remove.", status_code=404)
    update_customer_last_modified(customer_id, db)
    return {"message": "Profile picture removed successfully."}


@router.post("/logout")
def logout_customer(
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    if delete_bearer_token(customer=current_customer, db=db):
        # If the bearer token is deleted successfully, we can assume the logout was successful
        return {"message": "Logged out successfully"}

    raise CabboException("Logout failed", status_code=500)

