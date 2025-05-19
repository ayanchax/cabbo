from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.customer.customer_schema import CustomerCreate
from models.customer.customer_orm import Customer

def create_customer(data: CustomerCreate, db: Session) -> Customer:
    try:
            customer = Customer(
            name=data.name or "",  # Name can be empty during onboarding
            email=data.email,
            phone_number=data.phone_number
        )
            db.add(customer)
            db.commit()
            db.refresh(customer)
            return customer
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Error creating customer: " + str(e))

def is_existing_customer(phone_number: str, db: Session) -> bool:
    existing = db.query(Customer).filter(Customer.phone_number == phone_number).first()
    return existing is not None