from sqlalchemy.orm import Session
from models.customer.customer_schema import CustomerCreate, CustomerUpdate
from models.customer.customer_orm import Customer
from core.exceptions import CabboException
from datetime import datetime, timezone
from core.security import (
    generate_jwt_token,
    decode_jwt_token,
    generate_jwt_payload,
    JWT_EXPIRY_UNIT,
    JWT_EXPIRY_UNIT_TIME_FRAME,
)


def create_customer(
    data: CustomerCreate, db: Session, phone_verified=False, activate=False
) -> Customer:
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
        raise CabboException(
            f"Error creating customer: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def is_existing_customer(phone_number: str, db: Session) -> bool:
    existing = db.query(Customer).filter(Customer.phone_number == phone_number).first()
    return existing is not None


def get_active_customer_by_id(customer_id: str, db: Session) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.is_active == True)
        .first()
    )
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


def update_customer_profile(
    customer_id: str, payload: CustomerUpdate, db: Session
) -> Customer:
    try:
        customer = get_active_customer_by_id(customer_id, db)
        updated = False
        if payload.name is not None:
            if customer.name != payload.name:
                customer.name = payload.name
                updated = True
        if payload.email is not None:
            existing_customer = (
                db.query(Customer)
                .filter(Customer.email == payload.email, Customer.id != customer_id)
                .first()
            )
            if existing_customer:
                raise CabboException(
                    "Email already in use, this update will not happen.",
                    status_code=400,
                )
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
        raise CabboException(
            f"Error updating customer profile: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def get_active_customer_by_id_and_bearer_token(
    customer_id: str, bearer_token: str, db: Session
) -> Customer:
    try:
        return (
            db.query(Customer)
            .filter(
                Customer.id == customer_id,
                Customer.bearer_token == bearer_token,
                Customer.is_active == True,
            )
            .first()
        )
    except Exception as e:
        return None


def is_customer_logged_in(customer: Customer) -> bool:
    if not customer.bearer_token:
        return False
    try:
        decode_jwt_token(
            customer.bearer_token
        )  # Decode the JWT token and raise error if invalid or expired
        return True
    except Exception:
        return False


def generate_customer_jwt(
    customer: Customer,
    expires_in=JWT_EXPIRY_UNIT,
    expires_unit=JWT_EXPIRY_UNIT_TIME_FRAME.get("DAYS"),
) -> str:
    payload = generate_jwt_payload(
        sub=str(customer.id),
        identity=customer.phone_number,
        expires_in=expires_in,
        expires_unit=expires_unit,
    )
    return generate_jwt_token(payload)


def persist_bearer_token(customer: Customer, token: str, db: Session) -> str:
    try:
        customer.bearer_token = token
        customer.last_seen = datetime.now(timezone.utc)
        db.commit()
        db.refresh(customer)
        return token
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error persisting bearer token: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def delete_bearer_token(customer: Customer, db: Session) -> bool:
    try:
        customer.bearer_token = None
        db.commit()
        db.refresh(customer)
        return True
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error deleting bearer token: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def is_customer_email_verified(customer_id: str, db: Session) -> bool:
    try:
        customer = get_active_customer_by_id(customer_id, db)
        return customer.is_email_verified
    except Exception as e:
        raise CabboException(
            f"Error checking email verification status: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def mark_customer_email_verified(customer_id: str, db: Session) -> bool:
    try:
        customer = get_active_customer_by_id(customer_id, db)
        customer.is_email_verified = True
        customer.last_modified = datetime.now(timezone.utc)
        db.commit()
        db.refresh(customer)
        return True
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error marking email as verified: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def update_customer_last_modified(customer: Customer, db: Session):
    try:
        customer.last_modified = datetime.now(timezone.utc)
        db.commit()
        db.refresh(customer)
    except Exception as e:
        db.rollback()
    return customer
