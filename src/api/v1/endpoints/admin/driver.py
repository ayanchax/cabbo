from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Form,
    Form,
    Path,
    UploadFile,
    File,
)
from core.exceptions import CabboException
from core.security import ActiveInactiveStatusEnum, RoleEnum, validate_user_token
from db.database import a_yield_mysql_session, yield_mysql_session
from models.documents.kyc_document_enum import KYCDocumentTypeEnum
from models.driver.driver_schema import (
    DriverBaseSchema,
    DriverCreateSchema,
    DriverEarningSchema,
    DriverReadProfilePictureAfterUpdate,
    DriverReadSchema,
    DriverUpdateSchema,
)
from models.trip.trip_enums import TripStatusEnum
from models.user.user_orm import User
from sqlalchemy.orm import Session
from services.kyc_service import (
    list_kyc_documents,
    mark_kyc_verification_status_for_driver_document,
    remove_kyc_document_by_id_for_driver,
    update_driver_kyc_documents,
)
from services.driver_service import (
    activate_driver,
    create_driver,
    deactivate_driver,
    delete_driver,
    fetch_all_drivers_earnings_summary,
    fetch_all_trips_for_driver,
    get_all_drivers,
    get_all_drivers_by_availability,
    get_all_drivers_by_status,
    get_all_earnings_for_driver,
    get_average_rating_by_driver_id,
    get_driver_by_id,
    get_trip_earning_for_driver,
    update_driver,
    update_driver_last_modified,
)
from services.file_service import (
    remove_driver_profile_picture,
    save_driver_profile_picture,
)
from services.notification_service import notify_driver_onboarded
from services.orchestration_service import BackgroundTaskOrchestrator
from services.validation_service import validate_driver_payload
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# Add driver
@router.post("/create", response_model=DriverBaseSchema, status_code=201)
def add_driver(
    background_tasks: BackgroundTasks,
    payload: DriverCreateSchema = Depends(validate_driver_payload),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new driver."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to add drivers.", status_code=403
        )

    driver = create_driver(payload=payload, db=db, created_by=current_user_role)
    # Send welcome email in background if email is provided
    orchestrator = BackgroundTaskOrchestrator(background_tasks)
    orchestrator.add_task(
        notify_driver_onboarded, task_name="NotifyDriverOnboarded", driver=driver
    )

    return DriverBaseSchema.model_validate(driver)


# Edit driver
@router.put("/{driver_id}", response_model=DriverBaseSchema, status_code=200)
def edit_driver(
    driver_id: str,
    payload: DriverUpdateSchema = Depends(validate_driver_payload),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Edit driver details."""
    current_user_role = current_user.role
    if (
        current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]
        or driver_id == current_user.id
    ):
        driver = update_driver(driver_id=driver_id, payload=payload, db=db)
        return DriverBaseSchema.model_validate(driver)
    raise CabboException("You do not have permission to edit drivers.", status_code=403)


# Upload driver profile picture
@router.post(
    "/{driver_id}/profile-picture", response_model=DriverReadProfilePictureAfterUpdate
)
def upload_driver_profile_picture(
    driver_id: str = Path(..., description="ID of the driver"),
    file: UploadFile = File(..., description="Profile picture file"),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Upload driver profile picture."""

    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if not driver.is_active:
        raise CabboException(
            "Cannot upload profile picture for inactive driver", status_code=400
        )

    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        # Proceed with upload logic (e.g., save file to storage, update driver record with file path)
        image_url = save_driver_profile_picture(driver_id=driver_id, file=file)
        updated_driver = update_driver_last_modified(driver=driver, db=db)
        return DriverReadProfilePictureAfterUpdate(
            image_url=image_url, last_modified=updated_driver.last_modified
        )

    raise CabboException(
        "You do not have permission to upload driver profile picture.", status_code=403
    )


# Remove driver profile picture
@router.delete("/{driver_id}/profile-picture")
def delete_driver_profile_picture(
    driver_id: str = Path(..., description="ID of the driver"),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Remove driver profile picture."""

    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if not driver.is_active:
        raise CabboException(
            "Cannot upload profile picture for inactive driver", status_code=400
        )

    current_user_role = current_user.role

    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        # Proceed with removal logic (e.g., delete file from storage, update driver record)
        remove_driver_profile_picture(driver_id=driver_id)
        update_driver_last_modified(driver=driver, db=db)
        return {"message": "Profile picture removed successfully."}

    raise CabboException(
        "You do not have permission to remove driver profile picture.", status_code=403
    )


# View driver details/profile
@router.get("/{driver_id}", response_model=DriverReadSchema)
def view_driver_profile(
    driver_id: str = Path(..., description="ID of the driver"),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """View driver details/profile."""
    driver = get_driver_by_id(driver_id, db)

    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    current_user_role = current_user.role
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        return DriverReadSchema.model_validate(driver)

    raise CabboException(
        "You do not have permission to view this driver.", status_code=403
    )


# Upload driver kyc documents
@router.post("/{driver_id}/documents")
def upload_driver_documents(
    driver_id: str,
    files: list[UploadFile] = File(...),
    document_types: list[KYCDocumentTypeEnum] = Form(...),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if not driver.is_active:
        raise CabboException(
            "Cannot upload documents for inactive driver", status_code=400
        )

    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:

        return update_driver_kyc_documents(
            driver=driver, files=files, document_types=document_types, db=db
        )

    raise CabboException(
        "You do not* have permission to upload driver documents.", status_code=403
    )


# Remove driver kyc document
@router.delete("/{driver_id}/documents/{document_id}")
def remove_driver_document(
    driver_id: str,
    document_id: str,
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Remove a specific driver document."""
    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        if not driver.kyc_documents:
            raise CabboException("No documents found for this driver.", status_code=404)

        removed, error = remove_kyc_document_by_id_for_driver(driver, document_id, db)
        if not removed:
            raise CabboException(error or "Document not found.", status_code=404)
        return {"message": f"Document {document_id} removed for driver {driver_id}"}


# View driver kyc documents
@router.get("/{driver_id}/documents")
def view_driver_documents(
    driver_id: str,
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """View all kyc documents for a driver."""
    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        if not driver.kyc_documents:
            return []
        return list_kyc_documents(driver, db)

    raise CabboException(
        "You do not have permission to view driver documents.", status_code=403
    )


# mark kyc verified or unverified
@router.post("/{driver_id}/documents/{document_id}/verify/{status}")
def mark_kyc_verified(
    driver_id: str,
    document_id: str,
    status: bool,
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Mark a specific driver document as verified or unverified."""
    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        return mark_kyc_verification_status_for_driver_document(
            driver, document_id, status, db
        )
    raise CabboException(
        "You do not have permission to verify/unverify driver documents.",
        status_code=403,
    )


# Remove driver
@router.delete("/{driver_id}")
def remove_driver(
    driver_id: str = Path(..., description="ID of the driver"),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Remove a driver from the system."""

    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)

    if driver is None:
        raise CabboException("Driver not found", status_code=404)

    if driver.is_active:
        raise CabboException(
            "Cannot remove an active driver. Please deactivate the driver first.",
            status_code=400,
        )

    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        is_deleted = delete_driver(driver_id=driver_id, db=db)
        if is_deleted:
            return {"message": f"Driver {driver_id} removed (admin action)"}

    raise CabboException(
        "You do not have permission to remove this driver.", status_code=403
    )


# Activate driver
@router.post("/{driver_id}/activate")
def driver_activation(
    driver_id: str = Path(..., description="ID of the driver"),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Activate a driver."""
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if driver.is_active:
        raise CabboException("Driver is already active", status_code=400)

    if current_user.role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        updated_driver = activate_driver(driver_id=driver_id, db=db)
        return {
            "message": f"Driver '{updated_driver.name}' with id: {updated_driver.id} activated"
        }
    raise CabboException(
        "You do not have permission to activate this driver.", status_code=403
    )


# Deactivate driver
@router.post("/{driver_id}/deactivate")
def driver_deactivation(
    driver_id: str = Path(..., description="ID of the driver"),
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Deactivate a driver."""
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)

    if not driver.is_active:
        raise CabboException("Driver is already inactive", status_code=400)

    if current_user.role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        updated_driver = deactivate_driver(driver_id=driver_id, db=db)
        return {
            "message": f"Driver '{updated_driver.name}' with id: {updated_driver.id} deactivated"
        }

    raise CabboException(
        "You do not have permission to deactivate this driver.", status_code=403
    )


# List all drivers by their activation status
@router.get("/all/{status}")
def list_drivers_by_status(
    status: ActiveInactiveStatusEnum,
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all drivers by their activation status."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view drivers.", status_code=403
        )

    return get_all_drivers_by_status(status=status, db=db)


# List all drivers by their availability status
@router.get("/all/availability/{is_available}")
def list_drivers_by_availability(
    is_available: bool,
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all drivers by their availability status. This endpoint will enable to know which drivers are available for new trips and which are not and hence help in better trip assignment and management."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view drivers.", status_code=403
        )

    return get_all_drivers_by_availability(is_available=is_available, db=db)


# List all drivers
@router.get("/")
def list_drivers(
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all drivers (admin view)."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view drivers.", status_code=403
        )

    return get_all_drivers(db)


# View driver lifetime trips
@router.get("/{driver_id}/trips")
async def view_driver_trips_history(
    driver_id: str,
    status: Optional[TripStatusEnum] = None,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """LIST View trip history for a driver."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view driver trips.", status_code=403
        )
    return await fetch_all_trips_for_driver(driver_id=driver_id, status=status, db=db)


@router.get("/{driver_id}/average-rating", response_model=float)
async def get_average_rating_of_driver(
    driver_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get the average rating of a driver."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view driver ratings.", status_code=403
        )
    return await get_average_rating_by_driver_id(driver_id=driver_id, db=db)




# earning detail for a driver for a specific trip (admin audit)
@router.get("/{driver_id}/earning/trip/{trip_id}", response_model=DriverEarningSchema)
async def view_driver_earning_for_trip(
    driver_id: str,
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Object View earning for a specific trip for a driver."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.finance_admin,
    ]:
        raise CabboException(
            "You do not have permission to view driver earnings.", status_code=403
        )
    earning= await get_trip_earning_for_driver(
        driver_id=driver_id, trip_id=trip_id, db=db
    )
    if earning is None:
        raise CabboException(
            "Earnings not found for the specified driver and trip.", status_code=404
        )
    return DriverEarningSchema.model_validate(earning)


# all-time earnings for a driver (admin audit)
@router.get("/{driver_id}/earnings", response_model=list[DriverEarningSchema])
async def view_driver_earnings(
    driver_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """LIST View earnings for a driver."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.finance_admin,
    ]:
        raise CabboException(
            "You do not have permission to view driver earnings.", status_code=403
        )
    earnings= await get_all_earnings_for_driver(driver_id=driver_id, db=db)
    if not earnings:
        raise CabboException(
            "Earnings not found for the specified driver.", status_code=404
        )
    return [DriverEarningSchema.model_validate(e) for e in earnings]


# GET /earnings/summary — total across all drivers (finance admin visibility)
@router.get("/earnings/summary", response_model=dict)
async def view_earnings_summary(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """View earnings summary across all drivers."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise CabboException(
            "You do not have permission to view earnings summary.", status_code=403
        )
    return await fetch_all_drivers_earnings_summary(db=db)
    
