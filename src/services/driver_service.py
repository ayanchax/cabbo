from datetime import datetime, timezone
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.trip_helpers import get_trip_type_by_trip_type_id
from models.driver.driver_orm import Driver
from models.driver.driver_schema import DriverCreateSchema, DriverUpdateSchema
from core.security import ActiveInactiveStatusEnum, RoleEnum
import uuid

from models.map.location_schema import LocationInfo
from models.trip.trip_enums import TripStatusEnum
from models.trip.trip_orm import Trip
from models.user.user_orm import User
from services.audit_trail_service import log_trip_audit
from services.customer_service import get_customer_by_id
from services.geography_service import get_country_by_code
from services.geography_service import get_country_by_code


def create_driver(
    payload: DriverCreateSchema,
    db: Session,
    created_by: RoleEnum = RoleEnum.driver_admin,
) -> Driver:
    """Create a new driver."""
    try:

        driver = Driver(
            id=str(uuid.uuid4()),
            name=payload.name,
            phone=payload.phone,
            email=payload.email,
            gender=payload.gender,
            dob=payload.dob,
            emergency_contact_name=payload.emergency_contact_name,
            emergency_contact_number=payload.emergency_contact_number,
            nationality=payload.nationality,
            religion=payload.religion,
            fuel_type=payload.fuel_type,
            cab_type=payload.cab_type,
            cab_model_and_make=payload.cab_model_and_make,
            cab_registration_number=payload.cab_registration_number,
            cab_amenities=payload.amenities.model_dump() if payload.amenities else None,
            payment_mode=payload.payment_mode,
            payment_phone_number=payload.payment_phone_number,
            bank_details=(
                payload.bank_details.model_dump() if payload.bank_details else None
            ),
            address=payload.address.model_dump() if payload.address else None,
            is_active=True,
            is_available=True,
            created_by=created_by,
        )
        db.add(driver)
        db.commit()
        db.refresh(driver)
        return driver
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error creating driver: {str(e)}", status_code=500, include_traceback=True
        )


def get_driver_by_id(driver_id: str, db: Session) -> Driver:
    """Retrieve a driver by their ID."""
    return db.query(Driver).filter(Driver.id == driver_id).first()


def get_driver_by_phone(phone: str, db: Session) -> Driver:
    """Retrieve a driver by their phone number."""
    return db.query(Driver).filter(Driver.phone == phone).first()


def get_driver_by_email(email: str, db: Session) -> Driver:
    """Retrieve a driver by their email address."""
    return db.query(Driver).filter(Driver.email == email).first()


def get_all_drivers(db: Session):
    """Retrieve all drivers."""
    return db.query(Driver).all()


def get_all_active_drivers(db: Session):
    """Retrieve all active drivers."""
    return db.query(Driver).filter(Driver.is_active == True).all()


def get_all_drivers_by_availability(is_available: bool, db: Session):
    """Retrieve all drivers by their availability status."""
    return db.query(Driver).filter(Driver.is_available == is_available).all()


def get_all_drivers_by_status(status: ActiveInactiveStatusEnum, db: Session):
    """Retrieve all drivers by their active status."""

    if status == ActiveInactiveStatusEnum.active:
        return get_all_active_drivers(db)
    elif status == ActiveInactiveStatusEnum.inactive:
        return get_all_inactive_drivers(db)
    else:
        raise CabboException(
            "Invalid status. Use 'active' or 'inactive'.", status_code=400
        )


def get_all_inactive_drivers(db: Session):
    """Retrieve all inactive drivers."""
    return db.query(Driver).filter(Driver.is_active == False).all()


def update_driver(driver_id: str, payload: DriverUpdateSchema, db: Session) -> Driver:
    """Update an existing driver's details."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if hasattr(driver, field) and value is not None:
            setattr(driver, field, value)

    db.commit()
    db.refresh(driver)
    return driver


def delete_driver(driver_id: str, db: Session) -> bool:
    """Delete a driver by their ID."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    db.delete(driver)
    db.commit()
    return True


def activate_driver(driver_id: str, db: Session) -> Driver:
    """Activate a driver by their ID."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    driver.is_active = True
    db.commit()
    db.refresh(driver)
    return driver


def deactivate_driver(driver_id: str, db: Session) -> Driver:
    """Deactivate a driver by their ID."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    driver.is_active = False
    db.commit()
    db.refresh(driver)
    return driver


def update_driver_last_modified(driver: Driver, db: Session):
    try:
        driver.last_modified = datetime.now(timezone.utc)
        db.commit()
        db.refresh(driver)
    except Exception as e:
        db.rollback()
    return driver


def assign_driver_to_trip(trip: Trip, driver: Driver, db: Session, requestor: User):
    try:
        # Check Trip is in confirmed status
        if trip.status != TripStatusEnum.confirmed.value:
            raise CabboException(
                "Trip must be in confirmed status to assign a driver.", status_code=400
            )
        # Check Trip has a valid creator_id
        if not trip.creator_id:
            raise CabboException(
                "Trip does not have a valid creator to assign a driver.", status_code=400
            )
        # Check Trip creator is a customer
        if not trip.creator_type or trip.creator_type != RoleEnum.customer.value:
            raise CabboException(
                "Trip creator must be a customer to assign a driver.", status_code=400
            )
        # Check trip has a non-zero balance_payment, so that customer has paid advance and there is balance to be paid to driver
        if trip.balance_payment <= 0:
            raise CabboException(
                "Trip must have a non-zero balance payment to assign a driver.",
                status_code=400,
            )
        if trip.advance_payment <= 0:
            raise CabboException(
                "Trip must have a non-zero advance payment to assign a driver.",
                status_code=400,
            )
        # Check Driver is active
        if not driver.is_active:
            raise CabboException("Driver is not active.", status_code=400)
        
        # Check Driver is available
        if not driver.is_available:
            raise CabboException("Driver is not available.", status_code=400)
        
        # Check Driver has a valid phone number
        if not driver.phone or driver.phone.strip() == "":
            raise CabboException("Driver does not have a valid phone number.", status_code=400)
        
        # Check Driver is not already assigned to the trip
        if trip.driver_id==driver.id:
            raise CabboException("Driver is already assigned to this trip.", status_code=400)

        # When we have the driver app we will also check if the driver is kyc_verified or not.

        # Assign Driver to Trip
        # Once driver is assigned to trip, the trip status will still be confirmed until the driver admin marks the trip as ongoing after the driver informs the admin on trip start.
        # Since we have the driver_id assigned to a confirmed trip, we can easily find assigned trips for a driver without needing a sub status like 'assigned'. Moreover, we are logging this event in the trip audit log.
        # Later when we have the driver app, the driver can mark the trip as ongoing (post otp from customer) from the app which will update the trip status to ongoing. This will be done same way like Uber, Ola etc.
        trip.driver_id = driver.id 
        # Update Driver availability to False
        driver.is_available = False
        db.commit()
        db.refresh(trip)
        db.refresh(driver)
        log_trip_audit(
            trip_id=trip.id,
            status=trip.status,
            committer_id=requestor.id,
            reason=f"Driver {driver.name} assigned to trip.",
            changed_by=requestor.role,
            db=db,
        )  # Log the trip status audit entry
    
        
        return trip, driver
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error assigning driver to trip: {str(e)}", status_code=500, include_traceback=True
        )
    
def notify_customer_on_confirmed_trip_driver_assignment(trip:Trip, driver:Driver, db: Session):
    # Get customer email from trip.creator_id
    customer_id = trip.creator_id
    
    if not customer_id:
        print("Trip does not have a valid creator to notify customer.")
        return False
    
    customer = get_customer_by_id(customer_id, db)
    
    if not customer:
        print("Customer not found to notify on driver assignment.")
        return False
    
    if not customer.email or customer.email.strip() == "":
        print("Customer does not have a valid email to notify on trip confirmation and driver assignment. They will have to check the app for trip details.")
        return False
    
    
    trip_type = get_trip_type_by_trip_type_id(trip.trip_type_id, db)

    if not trip_type:
        print("Trip type not found for the trip to notify customer.")
        return False
    
    if not trip.origin or not trip.destination:
        print("Trip origin or destination not found to notify customer.")
        return False
    
    
    validated_origin = LocationInfo.model_validate(trip.origin)
    country = get_country_by_code(country_code=validated_origin.country_code, db=db)
    currency = country.currency_symbol or ""