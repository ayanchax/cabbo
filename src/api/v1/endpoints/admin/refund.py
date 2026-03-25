from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.policies.refund_enum import RefundStatus
from models.user.user_orm import User
from models.policies.refund_schema import RefundSchema
from sqlalchemy.ext.asyncio import AsyncSession
from services.payment_service import get_refund_status
from services.refund_service import fetch_all_refund_details, fetch_refund_detail_by_booking_id, fetch_refund_detail_by_booking_id_and_customer_id, fetch_refund_detail_by_refund_id, fetch_refund_details_by_customer_id, get_refund_details_by_trip_id, initiate_refund_by_booking_id

router = APIRouter()

# Get endpoint for refund details of a trip by booking_id
@router.get("/booking/{booking_id}", response_model=RefundSchema)
async def get_refund_details_by_booking_id(
    booking_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get refund details of a trip by booking_id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_detail = await fetch_refund_detail_by_booking_id(
        booking_id, db
    )
    if not refund_detail:
        raise HTTPException(status_code=404, detail="Refund details not found.")
    return refund_detail

# - Get endpoint for refund details of a trip by booking_id and customer_id  - finance_admin super admin
@router.get("/booking/{booking_id}/customer/{customer_id}", response_model=RefundSchema)
async def get_refund_details_by_booking_id_and_customer_id(
    booking_id: str | UUID,
    customer_id: str | UUID, 
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get refund details of a trip by booking_id and customer_id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_detail = await fetch_refund_detail_by_booking_id_and_customer_id(
        booking_id, customer_id, db
    )
    if not refund_detail:
        raise HTTPException(status_code=404, detail="Refund details not found.")
    return refund_detail

## - Get endpoint to list all refunds  - finance_admin  super admin
@router.get("/", response_model=list[RefundSchema])
async def list_all_refunds(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all refunds issued for a given customer_id for one or more trips."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_details = await fetch_all_refund_details(db)
    return refund_details

# - Get endpoint to list all refunds issued for a given customer_id for one or more trips - finance_admin, super_admin
@router.get("/customer/{customer_id}", response_model=list[RefundSchema])
async def list_all_refunds_by_customer_id(
    customer_id: str | UUID,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all refunds issued for a given customer_id for one or more trips."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_details = await fetch_refund_details_by_customer_id(customer_id, db)
    return refund_details


# - Get endpoint for fetching refund status of a trip from the payment provider by refund_id - finance_admin, super_admin
@router.get("/refund/{refund_id}/status", response_model=RefundStatus)
async def get_refund_status_by_refund_id(
    refund_id: str | UUID,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get refund status of a trip from the payment provider by refund_id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_status = get_refund_status(refund_id, db)
    if not refund_status:
        raise HTTPException(status_code=404, detail="Refund status not found.")
    return refund_status

# - Get endpoint for fetching refund detail by refund_id - finance_admin, super_admin
@router.get("/refund/{refund_id}", response_model=RefundSchema)
async def get_refund_detail_by_refund_id(
    refund_id: str | UUID,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get refund detail of a trip from the payment provider by refund_id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_detail = await fetch_refund_detail_by_refund_id(refund_id, db)
    if not refund_detail:
        raise HTTPException(status_code=404, detail="Refund detail not found.")
    return refund_detail

# - Get endpoint for getting refund_detail by trip_id - finance_admin, super_admin
@router.get("/trip/{trip_id}", response_model=RefundSchema)
async def get_refund_detail_by_trip_id(
    trip_id: str | UUID,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get refund detail of a trip from the payment provider by trip_id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_detail = await get_refund_details_by_trip_id(trip_id, db)
    if not refund_detail:
        raise HTTPException(status_code=404, detail="Refund detail not found.")
    return refund_detail

# Initiate a refund for a trip by booking_id - finance_admin, super_admin
@router.get("/booking/{booking_id}/initiate-refund")
async def init_refund_by_booking_id(
    booking_id: str | UUID,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Initiate a refund for a trip by booking_id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.finance_admin]:
        raise HTTPException(
            status_code=403, detail="You do not have permission to access this resource."
        )
    refund_initiated= await initiate_refund_by_booking_id(booking_id=booking_id, db=db, requestor=current_user.id)
    if not refund_initiated:
        raise HTTPException(status_code=400, detail="Refund initiation failed.")
    return {"message": "Refund initiation successful."}


