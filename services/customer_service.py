from sqlalchemy.orm import Session
from models.customer.customer_schema import CustomerCreate,CustomerUpdate
from models.customer.customer_orm import Customer
from core.exceptions import CabboException
from datetime import datetime, timedelta, timezone
from core.constants import APP_NAME
from core.security import generate_jwt_token
from services.otp_service import OTP_EXPIRY_MINUTES

def create_customer(data: CustomerCreate, db: Session,phone_verified=False, activate=False) -> Customer:
    try:
            customer = Customer(
            name=data.name or "",  # Name can be empty during onboarding
            email=data.email,
            phone_number=data.phone_number,
            is_phone_verified=phone_verified,  # True
            is_active=activate,  # True

        )
            db.add(customer)
            db.commit()
            db.refresh(customer)
            return customer
    except Exception as e:
        db.rollback()
        raise CabboException(f"Error creating customer: {str(e)}", status_code=500, include_traceback=True)

def is_existing_customer(phone_number: str, db: Session) -> bool:
    existing = db.query(Customer).filter(Customer.phone_number == phone_number).first()
    return existing is not None

def get_active_customer_by_id(customer_id: str, db: Session) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id, Customer.is_active == True).first()
    if not customer:
        raise CabboException("Customer not found", status_code=404)
    return customer
def get_customer_by_phone_number(phone_number: str, db: Session) -> Customer:
    customer = db.query(Customer).filter(Customer.phone_number == phone_number).first()
    if not customer:
        raise CabboException("Customer not found", status_code=404)
    return customer

def get_customer_by_id(customer_id: str, db: Session) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if not customer:
        raise CabboException("Customer not found", status_code=404)
    return customer

def update_customer_profile(customer_id: str, payload:CustomerUpdate, db: Session) -> Customer:
    try:
        customer = get_active_customer_by_id(customer_id, db)
        updated = False
        if payload.name is not None:
            if customer.name != payload.name:
                customer.name = payload.name
                updated = True
        if payload.email is not None:
            existing_customer = db.query(Customer).filter(Customer.email == payload.email , Customer.id!=customer_id).first()
            if existing_customer:
                    raise CabboException("Email already in use, this update will not happen.", status_code=400)
            if customer.email != payload.email:
                customer.email = payload.email
                customer.is_email_verified = False
                updated = True
        if updated:
            customer.last_modified = datetime.now(timezone.utc)
            db.commit()
            db.refresh(customer)
        return customer
    except Exception as e:
        db.rollback()
        raise CabboException(f"Error updating customer profile: {str(e)}", status_code=500, include_traceback=True)

def generate_customer_jwt(customer: Customer, expires_in=OTP_EXPIRY_MINUTES, expires_unit='days') -> str:
    # Generate JWT token with flexible expiry
    now = datetime.now(timezone.utc)
    if expires_unit == 'days':
        expire = now + timedelta(days=expires_in)
    elif expires_unit == 'hours':
        expire = now + timedelta(hours=expires_in)
    elif expires_unit == 'minutes':
        expire = now + timedelta(minutes=expires_in)
    else:
        expire = now + timedelta(days=OTP_EXPIRY_MINUTES)  # fallback
    payload = {
        "iss": APP_NAME,
        "iat": int(now.timestamp()),
        "sub": str(customer.id),
        "exp": int(expire.timestamp()),
        "phone_number": customer.phone_number
    }
    return generate_jwt_token(payload)