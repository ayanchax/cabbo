# Admin route allowed for cust_admin and super_admin for performing admin level tasks such as listing all customers, activate/deactivate customers, view customer trips
# Passenger management is done by customer themselves via customer routes, passenger has nothing to do with admin.

from typing import Literal
from fastapi import APIRouter
from fastapi.params import Depends

from core.security import validate_user_token
from db.database import a_yield_mysql_session
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter()


# Get all customers with filters
@router.get("/", response_model=list)
async def list_customers(
    status: Literal["active", "inactive"] = None,
    email_verified: bool = None,
    phone_verified: bool = None,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List customers with optional filters for status and verification."""
    pass


# Get customer profile by id
@router.get("/{customer_id}", response_model=dict)
async def get_customer_profile(
    customer_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get a customer's profile by their ID."""
    pass


# Activate a customer
@router.post("/{customer_id}/activate")
async def activate_customer(
    customer_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Activate a customer's account."""
    pass


# Deactivate a customer
@router.post("/{customer_id}/deactivate")
async def deactivate_customer(
    customer_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Deactivate a customer's account."""
    pass


# Suspend a customer account
@router.post("/{customer_id}/suspend")
async def suspend_customer(
    customer_id: str,
    payload: dict,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Suspend a customer's account."""
    pass
