from sqlalchemy.orm import Session
from core.exceptions import CabboException
from models.driver.driver_orm import Driver
from models.driver.driver_schema import DriverCreateSchema, DriverUpdateSchema
from core.security import RoleEnum
import uuid

def create_driver(payload: DriverCreateSchema, db: Session, created_by: RoleEnum = RoleEnum.driver_admin) -> Driver:
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
			car_type=payload.car_type,
			car_model=payload.car_model,
			car_registration_number=payload.car_registration_number,
			payment_mode=payload.payment_mode,
			payment_phone_number=payload.payment_phone_number,
			bank_details=payload.bank_details.model_dump() if payload.bank_details else None,
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
		raise CabboException(f"Error creating driver: {str(e)}", status_code=500, include_traceback=True)

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
