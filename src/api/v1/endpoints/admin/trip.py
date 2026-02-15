# - Admin based Trip endpoints, only super_admin
#     See trip by trip_id
#     List all trips in system
#     List trips by driver_id
#     List trips by customer_id
#     List trips by status
#     Update trip status
#     Assign driver to trip Done


from fastapi import APIRouter, BackgroundTasks, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import yield_mysql_session
from models.user.user_orm import User
from services.driver_service import assign_driver_to_trip, get_driver_by_id
from services.notification_service import notify_customer_booking_confirmed
from services.orchestration_service import BackgroundTaskOrchestrator
from services.trips.trip_service import get_trip_by_id
from sqlalchemy.orm import Session

router = APIRouter()


# View trip details by trip_id
@router.get("/{trip_id}")
def view_trip_details(
    trip_id: str,
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """View trip details by trip_id."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip details.", status_code=403
        )
    trip = get_trip_by_id(trip_id, db)
    if trip is None:
        raise CabboException("Trip not found", status_code=404)
    return trip


# Assign driver to trip
@router.post("/{trip_id}/assign-driver/{driver_id}")
def assign_driver(
    background_tasks: BackgroundTasks,
    trip_id: str,
    driver_id: str,
    db: Session = Depends(yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Assign a driver to a trip."""
    current_user_role = current_user.role
    trip = get_trip_by_id(trip_id, db)

    if trip is None:
        raise CabboException("Trip not found", status_code=404)
    driver = get_driver_by_id(driver_id, db)
    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to assign drivers to trips.", status_code=403
        )

    assigned_trip, assigned_driver = assign_driver_to_trip(
        trip=trip, driver=driver, db=db, requestor=current_user
    )

    # Background job to notify customer via email, if email is provided
    orchestrator = BackgroundTaskOrchestrator(background_tasks)
    orchestrator.add_task(
        notify_customer_booking_confirmed,
        task_name="NotifyCustomerOnBookingConfirmedAndDriverAssigned",
        booking=assigned_trip,
        db=db,
    )

    #  As of now, before assigning, driver admin will call the driver first, confirm their availability; and inform about the trip, final fare payout and customer manually. If they agree, driver admin will assign the trip to them.
    #  Not implementing extra notification system for driver at the moment to save cost.

    return {
        "message": f"Driver {assigned_driver.name} assigned to trip {assigned_trip.id}"
    }
