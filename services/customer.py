from sqlalchemy.orm import Session
from fastapi import HTTPException
from models.customer.customer_schema import CustomerCreate
from models.customer.customer_orm import Customer

def create_customer(data: CustomerCreate, db: Session) -> Customer:
    #Check if phone number already exists
    existing = db.query(Customer).filter(Customer.phone_number == data.phone_number).first()
    if existing:
        raise HTTPException(status_code=400, detail="Phone number already registered.")
    
    #For now, just create the customer with phone number
    customer = Customer(
        name=data.name or "",  # Name can be empty for now
        email=data.email,
        phone_number=data.phone_number
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer
