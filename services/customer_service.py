from sqlalchemy.orm import Session
from models.customer.customer_schema import CustomerCreate
from models.customer.customer_orm import Customer
from core.exceptions import CabboException

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