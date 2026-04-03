from fastapi import APIRouter, Depends, HTTPException
from core.security import validate_customer_token
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from models.policies.refund_schema import RefundSchema

from services.refund_service import fetch_refund_detail_by_booking_id_and_customer_id
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()

#Trip refund endpoints for customers to fetch refund details for their bookings. This will allow customers to view the status and details of their refunds in case of cancellations or other issues with their trips. This endpoint will validate the JWT token to ensure that only authenticated customers can access their refund details securely.

# Get endpoint for fetching refund details
@router.get("/refund/{booking_id}", response_model=RefundSchema)
async def get_refund_details(
    booking_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Fetch refund details for a specific booking.
    """
    refund_details = await fetch_refund_detail_by_booking_id_and_customer_id(
        booking_id=booking_id, requestor=current_customer.id, db=db
    )
    if not refund_details:
        raise HTTPException(
            status_code=404, detail="Refund details not found for the given booking ID."
        )
    return refund_details
