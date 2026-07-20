from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.exceptions import CabboException, UNAUTHORIZED
from core.security import RoleEnum, validate_user_token
from db.database import yield_mysql_session
from models.user.user_orm import User
from services.trips.booking_service import recover_payment_verified_temp_trip

router = APIRouter()


@router.post(
    "/payment-verified-temp-trip/{temp_trip_id}",
    response_model=dict,
    tags=["Admin Trip Recovery"],
)
def recover_payment_verified_booking(
    temp_trip_id: str,
    db: Session = Depends(yield_mysql_session),
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

    recovered_trip = recover_payment_verified_temp_trip(
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
