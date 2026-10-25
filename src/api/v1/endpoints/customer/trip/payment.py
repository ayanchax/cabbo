
from fastapi import APIRouter, BackgroundTasks, Depends, Response
from core.security import validate_customer_token
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from models.financial.payments_enum import ReconciliationStateEnum
from models.trip.trip_schema import (
    BookingPaymentStatus,
)
from services.trips.reconciliation_service import (
    a_get_booking_payment_status,
    a_process_booking_reconciliation_request,
    a_request_booking_reconciliation,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


#Trigger a reconciliation request
@router.post(
    "/{temp_trip_id}/reconcile",
    status_code=202,
    response_model=BookingPaymentStatus,
    response_model_exclude_none=True,
)
async def request_booking_reconciliation(
    temp_trip_id: str,
    response: Response,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """Persist a reconciliation request; return promptly while recovery runs independently."""
    result = await a_request_booking_reconciliation(
        temp_trip_id, current_customer.id, db
    )
    response.headers["Cache-Control"] = "no-store"
    if result.state == ReconciliationStateEnum.checking:
        background_tasks.add_task(
            a_process_booking_reconciliation_request, temp_trip_id, current_customer.id
        )
    return result


#Get booking payment status ideally after triggering a reconciliation request.
@router.get(
    "/status/{temp_trip_id}",
    response_model=BookingPaymentStatus,
    response_model_exclude_none=True,
)
async def booking_status(
    temp_trip_id: str,
    response: Response,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """Read stored booking/payment status without triggering reconciliation."""
    response.headers["Cache-Control"] = "no-store"
    return await a_get_booking_payment_status(temp_trip_id, current_customer.id, db)
