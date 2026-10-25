from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import CabboException, UNAUTHORIZED
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.user.user_orm import User
from models.trip.trip_schema import BookingPaymentStatus
from services.trips.reconciliation_service import a_reconcile_booking_as_admin
from services.trips.booking_service import a_recover_payment_verified_temp_trip

router = APIRouter()


@router.post(
    "/reconcile/{temp_trip_id}",
    response_model=BookingPaymentStatus,
    tags=["Admin Trip Recovery"],
)
async def reconcile_booking(
    temp_trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Check provider payment and recover a booking without a checkout callback.

    Uses normal throttling and fulfilment checks; does not override review or refund.
    """
    if current_user.role not in [RoleEnum.super_admin, RoleEnum.customer_admin, RoleEnum.finance_admin]:
        raise CabboException(
            "You do not have permission to reconcile bookings.",
            status_code=403,
            error_code=UNAUTHORIZED,
        )
    return await a_reconcile_booking_as_admin(temp_trip_id, current_user.id, db)


@router.post(
    "/payment-verified-temp-trip/{temp_trip_id}",
    response_model=dict,
    tags=["Admin Trip Recovery"],
)
async def recover_payment_verified_booking(
    temp_trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """
    Promote a payment-verified temporary trip to a confirmed trip.

    This is a manual recovery path for rare cases where Razorpay verification
    succeeded, but normal trip creation did not complete.
    """
    if current_user.role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to recover payment-verified bookings.",
            status_code=403,
            error_code=UNAUTHORIZED,
        )

    recovered_trip = await a_recover_payment_verified_temp_trip(
        temp_trip_id=temp_trip_id,
        admin_user_id=current_user.id,
        db=db,
    )
    return {
        "message": "Payment-verified booking recovered successfully.",
        "trip_id": recovered_trip.trip_id,
        "booking_id": recovered_trip.booking_id,
        "status": recovered_trip.status,
    }
