# - Admin based Trip endpoints, only super_admin
#     See trip by trip_id done
#     See trip by booking_id done (booking_id is the unique id from the booking system, which is used to create a trip in our system) done
#     List all trips in system done
#     List trips by driver_id done
#     List trips by customer_id done
#     List trips by status --
#     Update trip status --
#     Assign driver to trip Done


from fastapi import APIRouter, BackgroundTasks, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.user.user_orm import User
from services.driver_service import a_get_driver_by_id, assign_driver_to_trip
from services.notification_service import notify_customer_booking_confirmed
from services.orchestration_service import BackgroundTaskOrchestrator
from services.trips.trip_service import (
    async_get_all_trips,
    async_get_trip_by_booking_id,
    async_get_trip_by_id,
    async_get_trips_by_customer_id,
    async_get_trips_by_driver_id,
    serialize_trip,
    serialize_trips,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# View trip details by trip_id
@router.get("/{trip_id}")
async def view_trip_details(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
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
    trip = await async_get_trip_by_id(trip_id, db)
    if trip is None:
        raise CabboException("Trip not found", status_code=404)

    return serialize_trip(trip)


# View trip details by booking_id
@router.get("/booking/{booking_id}")
async def view_trip_details_by_booking_id(
    booking_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """View trip details by booking_id."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
        RoleEnum.customer,
    ]:
        raise CabboException(
            "You do not have permission to view trip details.", status_code=403
        )
    trip = await async_get_trip_by_booking_id(booking_id, db)

    if trip is None:
        raise CabboException("Trip booking not found", status_code=404)
    serialized_trip = serialize_trip(trip)
    if "id" in serialized_trip:
        serialized_trip.pop(
            "id"
        )  # Remove internal trip ID from the response for security reasons
    return serialized_trip


# List all trips in system
@router.get("/list/all", response_model=list)
async def list_all_trips(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all trips in the system."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view all trips.", status_code=403
        )
    trips = await async_get_all_trips(db)
    return serialize_trips(trips)


# List trips by driver_id - this will be used by driver admin to see all trips that belong to a particular driver, and also by super admin for any driver
@router.get("/list/by/driver/{driver_id}", response_model=list)
async def list_trips_by_driver_id(
    driver_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List trips by driver_id."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to view trips by driver.", status_code=403
        )
    trips = await async_get_trips_by_driver_id(driver_id, db)
    # Serialize trips and driver details
    return serialize_trips(trips)


# List trips by customer_id - this will be used by customer admin to see all trips that belong to a particular customer, and also by super admin for any customer, and also by customers to see their own trips
@router.get("/list/by/customer/{customer_id}", response_model=list)
async def list_trips_by_customer_id(
    customer_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List trips by customer_id."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.customer_admin,
        RoleEnum.customer,
    ]:
        raise CabboException(
            "You do not have permission to view trips by customer.", status_code=403
        )
    can_expose_customer_details = current_user_role in [
        RoleEnum.super_admin,
        RoleEnum.customer_admin,
    ]
    # Implementation to fetch and return trips by customer_id goes here
    trips = await async_get_trips_by_customer_id(
        customer_id, db, expose_customer_details=can_expose_customer_details
    )
    return serialize_trips(trips, expose_customer_details=can_expose_customer_details)


# Assign driver to trip
@router.post("/{trip_id}/assign-driver/{driver_id}")
async def assign_driver(
    background_tasks: BackgroundTasks,
    trip_id: str,
    driver_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Assign a driver to a trip."""
    current_user_role = current_user.role
    trip = await async_get_trip_by_id(trip_id, db)
    if trip is None:
        raise CabboException("Trip not found", status_code=404)
    driver = await a_get_driver_by_id(driver_id, db)

    if driver is None:
        raise CabboException("Driver not found", status_code=404)
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to assign drivers to trips.", status_code=403
        )

    assigned_trip, assigned_driver = await assign_driver_to_trip(
        trip=trip, driver=driver, db=db, requestor=current_user, attach_trip_relationships=True
    ) #Attaching trip relationships with customer details exposed, so that it can be used in the notification task to notify customer about driver assignment and trip confirmation

  
    # Background job to notify customer via email, if email is provided
    orchestrator = BackgroundTaskOrchestrator(background_tasks)
    orchestrator.add_task(
        notify_customer_booking_confirmed,
        task_name="NotifyCustomerOnBookingConfirmedAndDriverAssigned",
        booking=assigned_trip,
        
    )

    #  As of now, before assigning, driver admin will call the driver first, confirm their availability; and inform about the trip, final fare payout and customer manually. If they agree, driver admin will assign the trip to them.
    #  Not implementing extra notification system for driver at the moment to save cost. Driver admin can use the existing communication channels(phone) to inform the driver about the trip details and confirm  their availability before assignment

    return {
        "message": f"Driver {assigned_driver.name} assigned to trip {assigned_trip.booking_id} successfully."
    }
