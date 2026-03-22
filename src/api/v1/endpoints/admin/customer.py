# Admin route allowed for cust_admin and super_admin for performing admin level tasks such as listing all customers, activate/deactivate customers, view customer trips
# Passenger management is done by customer themselves via customer routes, passenger has nothing to do with admin.

from typing import Literal
from fastapi import APIRouter
from fastapi.params import Depends, Query

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.customer.customer_schema import CustomerRead, CustomerSuspensionRequest
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession

from services.customer_service import (
    async_activate_customer,
    async_deactivate_customer,
    async_get_all_customers,
    async_get_customer_by_id,
    async_suspend_customer,
)


router = APIRouter()


# Get all customers with filters
@router.get("/", response_model=list[CustomerRead])
async def list_customers(
    status: Literal["active", "inactive"] = Query(
        None, description="Filter customers by status: active or inactive"
    ),
    email_verified: bool = Query(
        None, description="Filter customers by email verification status"
    ),
    phone_verified: bool = Query(
        None, description="Filter customers by phone verification status"
    ),
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List customers with optional filters for status and verification."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to view customers.", status_code=403
        )
    customer_model = await async_get_all_customers(
        db=db,
        status=status,
        email_verified=email_verified,
        phone_verified=phone_verified,
    )
    if not customer_model or len(customer_model) == 0:
        raise CabboException(
            status_code=404, message="No customers found with the given filters"
        )
    schema = [CustomerRead.model_validate(customer) for customer in customer_model]
    return schema


# Get customer profile by id
@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer_profile(
    customer_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get a customer's profile by their ID."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to view this customer's profile.",
            status_code=403,
        )
    customer_model = await async_get_customer_by_id(customer_id=customer_id, db=db)
    if not customer_model:
        raise CabboException(status_code=404, message="Customer not found")

    return CustomerRead.model_validate(customer_model)


# Activate a customer
@router.patch("/{customer_id}/activate")
async def activate_customer(
    customer_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Activate a customer's account."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to activate customers.", status_code=403
        )
    success, error_message = await async_activate_customer(
        customer_id=customer_id, db=db
    )
    if error_message:
        raise CabboException(status_code=500, message=error_message)

    if not success:
        raise CabboException(status_code=500, message="Failed to activate customer")
    return {"message": "Customer activated successfully"}


# Deactivate a customer
@router.patch("/{customer_id}/deactivate")
async def deactivate_customer(
    customer_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Deactivate a customer's account."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to deactivate customers.", status_code=403
        )
    success, error_message = await async_deactivate_customer(
        customer_id=customer_id, db=db
    )
    if error_message:
        raise CabboException(status_code=500, message=error_message)
    if not success:
        raise CabboException(status_code=500, message="Failed to deactivate customer")
    return {"message": "Customer deactivated successfully"}


# Suspend a customer account
@router.post("/{customer_id}/suspend")
async def suspend_customer(
    customer_id: str,
    payload: CustomerSuspensionRequest,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Suspend a customer's account."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to suspend customers.", status_code=403
        )
    payload.customer_id = customer_id  # Ensure the customer_id from the path is used
    success, error_message = await async_suspend_customer(payload=payload, db=db)
    if error_message:
        raise CabboException(status_code=500, message=error_message)
    if not success:
        raise CabboException(status_code=500, message="Failed to suspend customer")
    return {"message": "Customer suspended successfully"}
