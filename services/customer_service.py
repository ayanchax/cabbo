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
            dob=data.dob if hasattr(data, "dob") else None,
            age=(
                calculate_customer_age(data)
                if hasattr(data, "dob") and data.dob
                else None
            ),
            gender=(
                data.gender.value
                if hasattr(data, "gender") and data.gender is not None
                else None
            ),
            emergency_contact_name=(
                data.emergency_contact_name
                if hasattr(data, "emergency_contact_name")
                else None
            ),
            emergency_contact_number=(
                data.emergency_contact_number
                if hasattr(data, "emergency_contact_number")
                else None
            ),
            opt_in_updates=(
                data.opt_in_updates if hasattr(data, "opt_in_updates") else False
            ),
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
        updated_flags = [
            # Primary fields that can be updated
            update_customer_name(payload, customer),
            update_email(customer_id, payload, customer, db),
            # Secondary fields that can be updated
            update_customer_dob(payload, customer),
            update_customer_gender(payload, customer),
            update_customer_emergency_contact(payload, customer),
            update_opt_in_status(payload, customer),
        ]
        if any(updated_flags):
            # If any field was updated, set last_modified to now and commit changes
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


def update_customer_name(payload: CustomerUpdate, customer: Customer):
    if payload.name is not None:
        if customer.name != payload.name:
            customer.name = payload.name
            return True
    return False


def update_email(
    customer_id: str,
    payload: CustomerUpdate,
    customer: Customer,
    db: Session,
):
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
            return True
    return False


def update_opt_in_status(payload: CustomerUpdate, customer: Customer):
    if payload.opt_in_updates is not None:
        if customer.opt_in_updates != payload.opt_in_updates:
            customer.opt_in_updates = payload.opt_in_updates
            return True
    return False


def update_customer_emergency_contact(payload: CustomerUpdate, customer: Customer):
    updated = False
    if payload.emergency_contact_name is not None:
        if customer.emergency_contact_name != payload.emergency_contact_name:
            customer.emergency_contact_name = payload.emergency_contact_name
            updated = True
    if payload.emergency_contact_number is not None:
        if customer.emergency_contact_number != payload.emergency_contact_number:
            customer.emergency_contact_number = payload.emergency_contact_number
            updated = True
    return updated


def update_customer_gender(payload: CustomerUpdate, customer: Customer):
    if payload.gender is not None:
        gender_value = (
            payload.gender.value if hasattr(payload.gender, "value") else payload.gender
        )
        if customer.gender != gender_value:
            customer.gender = gender_value
            return True
    return False


def update_customer_dob(payload: CustomerUpdate, customer: Customer):
    if payload.dob is not None:
        if customer.dob != payload.dob:
            customer.dob = payload.dob
            # Auto-calculate age if dob is provided
            customer.age = calculate_customer_age(payload)
            return True

    return False


def calculate_customer_age(payload: CustomerUpdate):
    today = datetime.now(timezone.utc).date()
    if payload.dob:
        try:
            dob_date = (
                payload.dob.date() if hasattr(payload.dob, "date") else payload.dob
            )
            return (
                today.year
                - dob_date.year
                - ((today.month, today.day) < (dob_date.month, dob_date.day))
            )

        except Exception:
            return None
    return None


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
