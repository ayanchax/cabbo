from typing import Literal, Optional
from sqlalchemy.orm import Session
from models.common import S3ObjectInfo
from models.customer.customer_schema import (
    AdminSafeReadCustomer,
    CustomerCreate,
    CustomerRead,
    CustomerSafeRead,
    CustomerSuspensionRequest,
    CustomerUpdate,
)
from models.customer.customer_orm import Customer
from core.exceptions import CabboException, USER_NOT_FOUND, GENERIC_EXCEPTION
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from models.trip.trip_enums import TripStatusEnum
from models.user.user_enum import GenderEnum
from services.customer_email_verification_service import (
    a_get_existing_email_verification_link,
)


async def a_create_customer(
    data: CustomerCreate, db: AsyncSession, phone_verified=False, activate=False
) -> Customer:
    try:
        customer = Customer(
            name=data.name or "",  # Name can be empty during onboarding
            email=data.email,
            phone_number=data.phone_number,
            is_phone_verified=phone_verified,  # True
            is_active=activate,  # True
            dob=data.dob if hasattr(data, "dob") else None,
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
        await db.commit()
        await db.refresh(customer)
        return customer
    except Exception as e:
        await db.rollback()
        raise e


async def a_is_existing_customer(phone_number: str, db: AsyncSession) -> bool:
    result = await db.execute(
        select(Customer).where(
            Customer.phone_number == phone_number,
            Customer.is_active == True,
            Customer.is_suspended == False,
        )
    )
    return result.scalar_one_or_none() is not None


def is_existing_customer(phone_number: str, db: Session) -> bool:
    existing = (
        db.query(Customer)
        .filter(
            Customer.phone_number == phone_number,
            Customer.is_active == True,
            Customer.is_suspended == False,
        )
        .first()
    )
    return existing is not None


def get_active_customer_by_id(customer_id: str, db: Session) -> Customer:
    customer = (
        db.query(Customer)
        .filter(Customer.id == customer_id, Customer.is_active == True)
        .first()
    )
    if not customer:
        raise CabboException(
            "Customer not found", status_code=404, error_code=USER_NOT_FOUND
        )
    return customer


async def a_get_active_customer_by_id(
    customer_id: str, db: AsyncSession
) -> Customer:
    result = await db.execute(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.is_active == True
        )
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise CabboException(
            "Customer not found",
            status_code=404,
            error_code=USER_NOT_FOUND
        )

    return customer


async def a_get_customer_by_phone_number(
    phone_number: str, db: AsyncSession, silently_fail: bool = False
) -> Optional[Customer]:
    if phone_number is None or phone_number.strip() == "":
        if silently_fail:
            return None
        raise CabboException(
            "Phone number is required", status_code=400, error_code=GENERIC_EXCEPTION
        )
    result = await db.execute(
        select(Customer).filter(
            Customer.phone_number == phone_number,
            Customer.is_active == True,
            Customer.is_suspended == False,
        )
    )
    if not result:
        if silently_fail:
            return None
        raise CabboException(
            "Customer not found", status_code=404, error_code=USER_NOT_FOUND
        )
    return result.scalar_one_or_none()


def update_customer_name(customer_id: str, new_name: str, db: Session):
    customer = get_active_customer_by_id(customer_id, db)
    if update_name(CustomerUpdate(name=new_name), customer):
        db.commit()
        db.refresh(customer)
    return customer.name


async def a_update_customer_name(customer_id: str, new_name: str, db: AsyncSession):
    customer =await a_get_active_customer_by_id(customer_id, db)
    if update_name(CustomerUpdate(name=new_name), customer):
        await db.commit()
        await db.refresh(customer)
    return customer.name



def update_customer_email(
    customer_id: str, new_email: str, db: Session, unverify_email: bool = True
):
    customer = get_active_customer_by_id(customer_id, db)
    if customer.email == new_email:
        return customer.email, False  # No update needed if email is the same
    customer.email = new_email
    if unverify_email:
        customer.is_email_verified = False
    db.commit()
    db.refresh(customer)
    return customer.email, True


async def a_update_customer_email(
    customer_id: str, new_email: str, db: AsyncSession, unverify_email: bool = True
):
    customer = await a_get_active_customer_by_id(customer_id, db)
    if customer.email == new_email:
        return customer.email, False  # No update needed if email is the same
    customer.email = new_email
    if unverify_email:
        customer.is_email_verified = False
    await db.commit()
    await db.refresh(customer)
    return customer.email, True


def update_customer_dob(customer_id: str, new_dob: datetime, db: Session):
    customer = get_active_customer_by_id(customer_id, db)
    if update_dob(CustomerUpdate(dob=new_dob), customer):
        db.commit()
        db.refresh(customer)
    return customer.dob


async def a_update_customer_dob(customer_id: str, new_dob: datetime, db: AsyncSession):
    customer = await a_get_active_customer_by_id(customer_id, db)
    if update_dob(CustomerUpdate(dob=new_dob), customer):
        await db.commit()
        await db.refresh(customer)
    return customer.dob


def update_customer_gender(customer_id, new_gender: GenderEnum, db: Session):
    customer = get_active_customer_by_id(customer_id, db)
    if update_gender(CustomerUpdate(gender=new_gender), customer):
        db.commit()
        db.refresh(customer)
    return customer.gender


async def a_update_customer_gender(customer_id, new_gender: GenderEnum, db: AsyncSession):
    customer = await a_get_active_customer_by_id(customer_id, db)
    if update_gender(CustomerUpdate(gender=new_gender), customer):
       await db.commit()
       await db.refresh(customer)
    return customer.gender


def update_customer_emergency_contact(
    customer_id, payload: CustomerUpdate, db: Session
):
    customer = get_active_customer_by_id(customer_id, db)
    if update_emergency_contact(payload, customer):
        db.commit()
        db.refresh(customer)
    return {
        "emergency_contact_name": customer.emergency_contact_name,
        "emergency_contact_number": customer.emergency_contact_number,
    }


async def a_update_customer_emergency_contact(
    customer_id, payload: CustomerUpdate, db: AsyncSession
):
    customer = await a_get_active_customer_by_id(customer_id, db)
    if update_emergency_contact(payload, customer):
        await db.commit()
        await db.refresh(customer)
    return {
        "emergency_contact_name": customer.emergency_contact_name,
        "emergency_contact_number": customer.emergency_contact_number,
    }


def update_customer_profile(
    customer_id: str, payload: CustomerUpdate, db: Session
) -> tuple[Customer, bool]:
    try:
        customer = get_active_customer_by_id(customer_id, db)
        updated_flags = [
            # Primary fields that can be updated
            update_name(payload, customer),
            update_email(customer_id, payload, customer, db),
            # Secondary fields that can be updated
            update_dob(payload, customer),
            update_gender(payload, customer),
            update_emergency_contact(payload, customer),
            update_opt_in_status(payload, customer),
        ]
        if any(updated_flags):
            # If any field was updated, set last_modified to now and commit changes
            customer.last_modified = datetime.now(timezone.utc)
            db.commit()
            db.refresh(customer)

        email_updated = updated_flags[
            1
        ]  # The second item in the list corresponds to email update
        return customer, email_updated
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error updating customer profile: {str(e)}",
            status_code=500,
            include_traceback=True,
            error_code=GENERIC_EXCEPTION,
        )




async def a_update_customer_profile(
    customer_id: str, payload: CustomerUpdate, db: AsyncSession
) -> tuple[Customer, bool]:
    try:
        customer = await a_get_active_customer_by_id(customer_id, db)
        updated_flags = [
            # Primary fields that can be updated
            update_name(payload, customer),
            await update_email(customer_id, payload, customer, db),
            # Secondary fields that can be updated
            update_dob(payload, customer),
            update_gender(payload, customer),
            update_emergency_contact(payload, customer),
            update_opt_in_status(payload, customer),
        ]
        if any(updated_flags):
            # If any field was updated, set last_modified to now and commit changes
            customer.last_modified = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(customer)

        email_updated = updated_flags[
            1
        ]  # The second item in the list corresponds to email update
        return customer, email_updated
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Error updating customer profile: {str(e)}",
            status_code=500,
            include_traceback=True,
            error_code=GENERIC_EXCEPTION,
        )


def update_name(payload: CustomerUpdate, customer: Customer):
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
                "Email already in use by some other customer, this update will not happen.",
                status_code=400,
                error_code=GENERIC_EXCEPTION,
            )
        if customer.email != payload.email:
            customer.email = payload.email
            customer.is_email_verified = False
            return True
    return False


async def a_update_email(
    customer_id: str,
    payload: CustomerUpdate,
    customer: Customer,
    db: AsyncSession,
):
    if payload.email is not None:
        result = await db.execute(
            select(Customer).where(
                Customer.email == payload.email,
                Customer.id != customer_id
            )
        )
        existing_customer = result.scalar_one_or_none()

        if existing_customer:
            raise CabboException(
                "Email already in use by some other customer, this update will not happen.",
                status_code=400,
                error_code=GENERIC_EXCEPTION,
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


def update_emergency_contact(payload: CustomerUpdate, customer: Customer):
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


def update_gender(payload: CustomerUpdate, customer: Customer):
    if payload.gender is not None:
        gender_value = (
            payload.gender.value if hasattr(payload.gender, "value") else payload.gender
        )
        if customer.gender != gender_value:
            customer.gender = gender_value
            return True
    return False


def update_dob(payload: CustomerUpdate, customer: Customer):
    if payload.dob is not None:
        if customer.dob != payload.dob:
            customer.dob = payload.dob
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


 
def is_customer_email_verified(customer_id: str, db: Session) -> bool:
    try:
        customer = get_active_customer_by_id(customer_id, db)
        return customer.is_email_verified
    except Exception as e:
        raise CabboException(
            f"Error checking email verification status: {str(e)}",
            status_code=500,
            include_traceback=True,
            error_code=GENERIC_EXCEPTION,
        )

async def a_is_customer_email_verified(customer_id: str, db: AsyncSession) -> bool:
    try:
        customer = await a_get_active_customer_by_id(customer_id, db)
        return customer.is_email_verified
    except Exception as e:
        raise CabboException(
            f"Error checking email verification status: {str(e)}",
            status_code=500,
            include_traceback=True,
            error_code=GENERIC_EXCEPTION,
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
            error_code=GENERIC_EXCEPTION,
        )


async def a_mark_customer_email_verified(customer_id: str, db: AsyncSession) -> bool:
    try:
        customer = await a_get_active_customer_by_id(customer_id, db)
        customer.is_email_verified = True
        customer.last_modified = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(customer)
        return True
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Error marking email as verified: {str(e)}",
            status_code=500,
            include_traceback=True,
            error_code=GENERIC_EXCEPTION,
        )


def update_customer_profile_picture(
    customer: Customer, db: Session, s3_image_info: S3ObjectInfo = None
):
    try:
        customer.s3_image_info = s3_image_info.model_dump() if s3_image_info else None
        db.commit()
        db.refresh(customer)
        return customer
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error updating customer profile picture info: {str(e)}",
            status_code=500,
            include_traceback=True,
            error_code=GENERIC_EXCEPTION,
        )


async def a_update_customer_profile_picture(
    customer: Customer, db: AsyncSession, s3_image_info: S3ObjectInfo = None
):
    try:
        customer.s3_image_info = s3_image_info.model_dump() if s3_image_info else None
        await db.commit()
        await db.refresh(customer)
        return customer
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Error updating customer profile picture info: {str(e)}",
            status_code=500,
            include_traceback=True,
            error_code=GENERIC_EXCEPTION,
        )



async def async_get_all_customers(
    db: AsyncSession,
    status: Optional[Literal["active", "inactive"]] = None,
    email_verified: Optional[bool] = None,
    phone_verified: Optional[bool] = None,
):
    try:
        query = select(Customer)
        if status is not None:
            if status == "active":
                query = query.where(Customer.is_active == True)
            elif status == "inactive":
                query = query.where(Customer.is_active == False)
        if email_verified is not None:
            query = query.where(Customer.is_email_verified == email_verified)
        if phone_verified is not None:
            query = query.where(Customer.is_phone_verified == phone_verified)
        result = await db.execute(query)
        return result.scalars().all()
    except Exception as e:
        return []


async def async_get_customer_by_id(customer_id: str, db: AsyncSession):
    try:
        query = select(Customer).where(Customer.id == customer_id)
        result = await db.execute(query)
        return result.scalar_one_or_none()
    except Exception as e:
        return None


async def async_activate_customer(customer_id: str, db: AsyncSession) -> bool:
    try:
        customer = await async_get_customer_by_id(customer_id, db)
        if not customer:
            return False, "Customer not found"
        if customer.is_active:
            return False, "Customer is already active"

        customer.is_active = True
        customer.last_modified = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(customer)
        return True, None

    except Exception as e:
        return False, f"Error activating customer: {str(e)}"


async def async_deactivate_customer(customer_id: str, db: AsyncSession) -> bool:
    try:
        customer = await async_get_customer_by_id(customer_id, db)
        if not customer:
            return False, "Customer not found"
        if not customer.is_active:
            return False, "Customer is already inactive"

        customer.is_active = False
        customer.last_modified = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(customer)
        return True, None

    except Exception as e:
        return False, f"Error deactivating customer: {str(e)}"


async def async_suspend_customer(
    payload: CustomerSuspensionRequest, db: AsyncSession
) -> bool:
    try:
        if not payload.customer_id:
            return False, "Customer ID is required for suspension"
        customer = await async_get_customer_by_id(payload.customer_id, db)
        if not customer:
            return False, "Customer not found"
        if customer.is_suspended:
            return False, "Customer is already suspended"

        customer.is_suspended = True
        customer.suspension_reason = payload.reason or "No reason provided"
        customer.last_modified = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(customer)
        return True, None

    except Exception as e:
        return False, f"Error suspending customer: {str(e)}"


def get_customer_email(customer: CustomerRead):
    return customer.email if customer.email else None


def _get_customer_profile_picture_url(customer) -> Optional[str]:
    try:
        s3_image_info = (
            customer.get("s3_image_info")
            if isinstance(customer, dict)
            else getattr(customer, "s3_image_info", None)
        )

        if not s3_image_info:
            return None

        if isinstance(s3_image_info, dict):
            return s3_image_info.get("url")

        if isinstance(s3_image_info, S3ObjectInfo):
            return s3_image_info.url

        return getattr(s3_image_info, "url", None)
    except Exception:
        return None


def serialize_customer(customer, trip_dict: dict):
    customer = CustomerRead.model_validate(customer)
    customer_data = customer.model_dump()
    trip_dict["customer"] = customer_data
    trip_dict.pop("creator_id", None)
    trip_dict.pop("creator_type", None)
    return trip_dict


def serialize_customer_for_admin_retrieval(customer, trip_dict: dict):
    profile_picture_url = _get_customer_profile_picture_url(customer)
    customer = AdminSafeReadCustomer.model_validate(customer)
    customer.profile_picture_url = profile_picture_url

    customer_data = customer.model_dump(exclude_none=True, exclude_unset=True)
    trip_dict["customer"] = customer_data
    trip_dict.pop("creator_id", None)
    trip_dict.pop("creator_type", None)
    trip_dict.pop("opt_in_updates", None)

    return trip_dict


 
async def a_transform_to_safe_customer(customer: Customer, db: AsyncSession) -> CustomerSafeRead:
    
    safe_customer = CustomerSafeRead.model_validate(customer)
    safe_customer.profile_picture_url = _get_customer_profile_picture_url(customer)
    safe_customer.joined_on = customer.created_at
    actual_trips = (
        [
            trip
            for trip in customer.trips
            if trip.status
            not in [TripStatusEnum.cancelled.value, TripStatusEnum.dispute.value]
            and trip.is_active
        ]
        if hasattr(customer, "trips")
        else []
    )
    safe_customer.number_of_trips = len(actual_trips)
    existing_valid_email_verification = await a_get_existing_email_verification_link(
        customer.id, db=db
    )  # Check for existing email verification link

    can_reinitiate_email_verification = False  # Default to False

    if not customer.is_email_verified and not existing_valid_email_verification:
        # If email is not verified and no existing valid email verification link exists, the customer can reinitiate email verification.
        can_reinitiate_email_verification = True

    safe_customer.can_reinitiate_email_verification = can_reinitiate_email_verification
    return safe_customer
