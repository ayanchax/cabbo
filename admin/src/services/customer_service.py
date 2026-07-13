from typing import Literal, Optional
from sqlalchemy.orm import Session
from cabbo_core.models.customer.customer_schema import (
    CustomerRead,
    CustomerSuspensionRequest,
)
from cabbo_core.models.customer.customer_orm import Customer
from cabbo_core.exceptions import CabboException, USER_NOT_FOUND
from datetime import datetime, timezone
 
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select


    


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


def get_customer_by_phone_number(
    phone_number: str, db: Session, silently_fail: bool = False
) -> Customer:
    customer = (
        db.query(Customer)
        .filter(
            Customer.phone_number == phone_number,
            Customer.is_active == True,
            Customer.is_suspended == False,
        )
        .first()
    )
    if not customer:
        if silently_fail:
            return None
        raise CabboException(
            "Customer not found", status_code=404, error_code=USER_NOT_FOUND
        )
    return customer


def get_customer_by_id(customer_id: str, db: Session) -> Customer:
    customer = (
        db.query(Customer)
        .filter(
            Customer.id == customer_id,
            Customer.is_active == True,
            Customer.is_suspended == False,
        )
        .first()
    )
    if not customer:
        raise CabboException(
            "Customer not found", status_code=404, error_code=USER_NOT_FOUND
        )
    return customer


async def a_get_customer_by_id(customer_id: str, db: AsyncSession) -> Customer:
    result = await db.execute(
        select(Customer).filter(
            Customer.id == customer_id,
            Customer.is_active == True,
            Customer.is_suspended == False,
        )
    )
    customer = result.scalar_one_or_none()
    if not customer:
        raise CabboException(
            "Customer not found", status_code=404, error_code=USER_NOT_FOUND
        )
    return customer


 


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


def serialize_customer(customer, trip_dict: dict):
    customer = CustomerRead.model_validate(customer)
    customer_data = customer.model_dump()
    trip_dict["customer"] = customer_data
    trip_dict.pop("creator_id", None)
    trip_dict.pop("creator_type", None)
    return trip_dict


 