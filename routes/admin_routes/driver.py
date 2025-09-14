from fastapi import APIRouter, BackgroundTasks, Body, Depends, Path, UploadFile, File
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import get_mysql_session
from models.driver.driver_schema import DriverBaseSchema, DriverCreateSchema, DriverReadProfilePictureAfterUpdate, DriverReadSchema, DriverUpdateSchema
from models.user.user_orm import User
from sqlalchemy.orm import Session
from core.constants import APP_NAME
from services.driver_service import activate_driver, create_driver, deactivate_driver, delete_driver, get_driver_by_id, update_driver, update_driver_last_modified
from services.file_service import remove_driver_profile_picture, save_driver_profile_picture
from services.message_service import WELCOME_EMAIL_FILE, send_email

router = APIRouter(prefix="/admin/driver", tags=["Admin: Driver"])

# Add driver
@router.post("/create", response_model=DriverBaseSchema, status_code=201)
def add_driver(background_tasks: BackgroundTasks,payload: DriverCreateSchema = Body(...), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Add a new driver."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
            raise CabboException("You do not have permission to add drivers.", status_code=403)
    driver = create_driver(payload=payload, db=db, created_by=current_user_role)
    #Send welcome email in background if email is provided
    if driver.email and driver.name:
        subject = f"Welcome to {APP_NAME}!"
        from services.message_service import render_email_template

        html_content = render_email_template(
            WELCOME_EMAIL_FILE,
            for_driver=True,
            name=driver.name,
            app_name=APP_NAME.capitalize()
        )
        background_tasks.add_task(send_email, driver.email, subject, html_content)

    return DriverBaseSchema.model_validate(driver)

# Edit driver
@router.put("/{driver_id}", response_model=DriverBaseSchema, status_code=200)
def edit_driver(driver_id: str, payload: DriverUpdateSchema = Body(...), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Edit driver details."""
    current_user_role = current_user.role
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin] or driver_id==current_user.id:
        driver = update_driver(driver_id=driver_id, payload=payload, db=db)
        return DriverBaseSchema.model_validate(driver)
    raise CabboException("You do not have permission to edit drivers.", status_code=403)


# Upload driver profile picture
@router.post("/{driver_id}/profile-picture", response_model=DriverReadProfilePictureAfterUpdate)
def upload_driver_profile_picture(
    driver_id: str = Path(..., description="ID of the driver"),
    file: UploadFile = File(..., description="Profile picture file"),
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Upload driver profile picture."""
    
    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if not driver.is_active:
        raise CabboException("Cannot upload profile picture for inactive driver", status_code=400)
    
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin] or driver.id==current_user.id:
        # Proceed with upload logic (e.g., save file to storage, update driver record with file path)
        image_url = save_driver_profile_picture(driver_id=driver_id, file=file)
        updated_driver = update_driver_last_modified(driver=driver, db=db)
        return DriverReadProfilePictureAfterUpdate(image_url=image_url, last_modified=updated_driver.last_modified)

    raise CabboException("You do not have permission to upload driver profile picture.", status_code=403)
    

# Remove driver profile picture
@router.delete("/{driver_id}/profile-picture")
def delete_driver_profile_picture(driver_id: str=Path(..., description="ID of the driver"),
    db: Session = Depends(get_mysql_session), current_user: User = Depends(validate_user_token)):
    """Remove driver profile picture."""
    
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if not driver.is_active:
        raise CabboException("Cannot upload profile picture for inactive driver", status_code=400)
    
    current_user_role = current_user.role

    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin] or driver.id==current_user.id:
        # Proceed with removal logic (e.g., delete file from storage, update driver record)
        remove_driver_profile_picture(driver_id=driver_id)
        update_driver_last_modified(driver=driver, db=db)
        return {"message": "Profile picture removed successfully."}
    
    raise CabboException("You do not have permission to remove driver profile picture.", status_code=403)

# View driver details/profile
@router.get("/{driver_id}", response_model=DriverReadSchema)
def view_driver_profile(driver_id: str=Path(..., description="ID of the driver"), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """View driver details/profile."""
    driver = get_driver_by_id(driver_id, db)

    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    current_user_role = current_user.role
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin] or driver.id==current_user.id:
        return DriverReadSchema.model_validate(driver)
         
    raise CabboException("You do not have permission to view this driver.", status_code=403)

# Upload driver kyc documents
@router.post("/{driver_id}/documents")
def upload_driver_documents(driver_id: str):
    """Upload driver kyc documents."""
    return {"message": f"Documents uploaded for driver {driver_id}"}

# Remove driver kyc document
@router.delete("/{driver_id}/documents/{document_id}")
def remove_driver_document(driver_id: str, document_id: str):
    """Remove a specific driver document."""
    return {"message": f"Document {document_id} removed for driver {driver_id}"}

# View driver kyc documents
@router.get("/{driver_id}/documents")
def view_driver_documents(driver_id: str):
    """View all kyc documents for a driver."""
    return {"message": f"KYC documents for driver {driver_id}"}

# mark kyc verified
@router.post("/{driver_id}/documents/{document_id}/verify")
def mark_kyc_verified(driver_id: str, document_id: str):
    """Mark a specific driver document as verified."""
    return {"message": f"Document {document_id} verified for driver {driver_id}"}

# Mark kyc unverified
@router.post("/{driver_id}/documents/{document_id}/unverify")
def mark_kyc_unverified(driver_id: str, document_id: str):
    """Mark a specific driver document as unverified."""
    return {"message": f"Document {document_id} unverified for driver {driver_id}"}

# mark all kyc documents verified
@router.post("/{driver_id}/documents/verify-all")
def mark_all_kyc_verified(driver_id: str):
    """Mark all kyc documents for a driver as verified."""
    #This will automatically set overall kyc status to verified as well
    return {"message": f"All documents verified for driver {driver_id}"}

# mark all kyc documents unverified
@router.post("/{driver_id}/documents/unverify-all")
def mark_all_kyc_unverified(driver_id: str):
    """Mark all kyc documents for a driver as unverified."""
    #This will automatically set overall kyc status to unverified as well
    return {"message": f"All documents unverified for driver {driver_id}"}

# Update overall kyc status
# (Usually this will be auto managed based on individual document statuses, but in case admin wants to override)
@router.post("/{driver_id}/documents/kyc-status/{status}")
def update_kyc_status(driver_id: str, status: bool):
    """Update overall kyc status for a driver."""
    return {"message": f"KYC status for driver {driver_id} updated to {status}"}

# Remove driver
@router.delete("/{driver_id}")
def remove_driver(driver_id: str=Path(..., description="ID of the driver"), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Remove a driver from the system."""

    current_user_role = current_user.role
    driver = get_driver_by_id(driver_id, db)

    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    
    if driver.is_active:
        raise CabboException("Cannot remove an active driver. Please deactivate the driver first.", status_code=400)
    
    if driver.id==current_user.id:
        raise CabboException("You cannot remove yourself.", status_code=403)
    
    if current_user_role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        is_deleted = delete_driver(driver_id=driver_id, db=db)
        if is_deleted:
            return {"message": f"Driver {driver_id} removed (admin action)"}
    
    raise CabboException("You do not have permission to remove this driver.", status_code=403)

# Activate driver
@router.post("/{driver_id}/activate")
def driver_activation(driver_id: str=Path(..., description="ID of the driver"), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Activate a driver."""
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if driver.is_active:
        raise CabboException("Driver is already active", status_code=400)
    if driver.id == current_user.id:
        raise CabboException("You cannot activate yourself.", status_code=403)
    if current_user.role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        updated_driver = activate_driver(driver_id=driver_id, db=db)
        return {"message": f"Driver '{updated_driver.name}' with id: {updated_driver.id} activated"}
    raise CabboException("You do not have permission to activate this driver.", status_code=403)

# Deactivate driver
@router.post("/{driver_id}/deactivate")
def driver_deactivation(driver_id: str=Path(..., description="ID of the driver"), db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)):
    """Deactivate a driver."""
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)

    if not driver.is_active:
        raise CabboException("Driver is already inactive", status_code=400)

    if driver.id == current_user.id:
        raise CabboException("You cannot deactivate yourself.", status_code=403)

    if current_user.role in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        updated_driver = deactivate_driver(driver_id=driver_id, db=db)
        return {"message": f"Driver '{updated_driver.name}' with id: {updated_driver.id} deactivated"}

    raise CabboException("You do not have permission to deactivate this driver.", status_code=403)


# List all active drivers
@router.get("/drivers/active")
def list_active_drivers():
    """List all active drivers."""
    return {"message": "List of active drivers"}

# List all inactive drivers
@router.get("/drivers/inactive")
def list_inactive_drivers():
    """List all inactive drivers."""
    return {"message": "List of inactive drivers"}

# List all drivers
@router.get("/drivers")
def list_drivers():
    """List all drivers (admin view)."""
    return {"message": "List of drivers (admin view)"}

# Assign driver to trip
@router.post("/{driver_id}/trips/{trip_id}/assign")
def assign_driver_to_trip(trip_id: str):
    """Assign a driver to a trip."""
    return {"message": f"Driver assigned to trip {trip_id}"}

# Unassign driver from trip
@router.post("/{driver_id}/trips/{trip_id}/unassign")
def unassign_driver_from_trip(trip_id: str):
    """Unassign driver from a trip."""
    return {"message": f"Driver unassigned from trip {trip_id}"}

# View driver lifetime trips
@router.get("/{driver_id}/trips")
def view_driver_trips_history(driver_id: str):
    """LIST View trip history for a driver."""
    return {"message": f"Trip history for driver {driver_id}"}

# View driver ratings/feedback for a driver against all trips by all customers
@router.get("/{driver_id}/ratings")
def view_driver_ratings(driver_id: str):
    """LIST View ratings and feedback for a driver."""
    return {"message": f"Ratings/feedback for driver {driver_id}"}

# View driver ratings by a specific customer for a driver against all trips
@router.get("/{driver_id}/ratings/customer/{customer_id}")
def view_driver_ratings_by_customer(driver_id: str, customer_id: str):
    """LIST View ratings given by customers for a driver."""
    return {"message": f"Customer ratings for driver {driver_id} by customer {customer_id}"}

# View driver ratings for a specific trip
@router.get("/{driver_id}/ratings/trip/{trip_id}")
def view_driver_ratings_by_trip(driver_id: str, trip_id: str):
    """Object View ratings for a specific trip for a driver."""
    return {"message": f"Ratings for driver {driver_id} on trip {trip_id}"}

# View overall driver earnings for a driver for all trips
@router.get("/{driver_id}/earnings")
def view_driver_earnings(driver_id: str):
    """LIST View earnings for a driver."""
    return {"message": f"Earnings for driver {driver_id}"}

# View driver earnings for a specific trip
@router.get("/{driver_id}/earnings/trip/{trip_id}")
def view_driver_earnings_for_trip(driver_id: str, trip_id: str):
    """Object View earnings for a specific trip for a driver."""
    return {"message": f"Earnings for driver {driver_id} on trip {trip_id}"}
