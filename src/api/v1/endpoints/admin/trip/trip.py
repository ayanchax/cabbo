from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends

from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.trip.trip_enums import TripStatusEnum
from models.trip.trip_schema import AdditionalDetailsOnTripStatusChange
from models.user.user_orm import User
from services.driver_service import a_get_driver_by_id, assign_driver_to_trip
from services.notification_service import notify_customer_booking_confirmed
from services.orchestration_service import BackgroundTaskOrchestrator
from services.trips.trip_service import (
    activate_trip,
    async_get_all_trips,
    async_get_trip_by_booking_id,
    async_get_trip_by_id,
    async_get_trips_by_customer_id,
    async_get_trips_by_driver_id,
    delete_trip,
    serialize_trip,
    serialize_trips,
    update_trip_status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from . import reviews, refunds, dispute

router = APIRouter()


# View trip details by trip_id
@router.get("/{trip_id}", tags=["Admin Trip Management"])
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
@router.get("/booking/{booking_id}", tags=["Admin Trip Management"])
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
@router.get("/list/all", response_model=list, tags=["Admin Trip Management"])
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
    if not trips:
        raise CabboException("No trips found in the system", status_code=404)
    return serialize_trips(trips)


# List trips by driver_id - this will be used by driver admin to see all trips that belong to a particular driver, and also by super admin for any driver
@router.get(
    "/list/by/driver/{driver_id}", response_model=list, tags=["Admin Trip Management"]
)
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
    if not trips:
        raise CabboException("No trips found for the driver", status_code=404)
    # Serialize trips and driver details
    return serialize_trips(trips)


# List trips by customer_id - this will be used by customer admin to see all trips that belong to a particular customer, and also by super admin for any customer
@router.get(
    "/list/by/customer/{customer_id}",
    response_model=list | dict,
    tags=["Admin Trip Management"],
)
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
    if not trips:
        raise CabboException("No trips found for the customer", status_code=404)

    return serialize_trips(trips, expose_customer_details=can_expose_customer_details)


# List trips of customer by status: super_admin, customer_admin
@router.get(
    "/list/by/customer/{customer_id}/status/{status}",
    response_model=list | dict,
    tags=["Admin Trip Management"],
)
async def list_trips_by_customer_id_and_status(
    customer_id: str,
    status: TripStatusEnum,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List trips of customer by status."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.customer_admin,
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
    if not trips:
        raise CabboException("No trips found for the customer", status_code=404)

    serialized_trips = serialize_trips(
        trips, expose_customer_details=can_expose_customer_details
    )
    filtered_trips = [
        trip for trip in serialized_trips if trip.get("status") == status.value
    ]
    if not filtered_trips:
        raise CabboException(
            f"No trips found for the customer with status {status.value}",
            status_code=404,
        )

    return filtered_trips


# List trips by status: super_admin and customer_admin
@router.get(
    "/list/by/status/{status}", response_model=list, tags=["Admin Trip Management"]
)
async def list_trips_by_status(
    status: TripStatusEnum,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List trips by status."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.customer_admin]:
        raise CabboException(
            "You do not have permission to view trips by status.", status_code=403
        )
    trips = await async_get_all_trips(db)
    if not trips:
        raise CabboException("No trips found in the system", status_code=404)
    serialized_trips = serialize_trips(trips)
    filtered_trips = [
        trip for trip in serialized_trips if trip.get("status") == status.value
    ]
    if not filtered_trips:
        raise CabboException(
            f"No trips found with status {status.value}", status_code=404
        )
    return filtered_trips


# Update trip status - super_admin, driver_admin
@router.patch("/{trip_id}/status/{status}", tags=["Admin Trip Management"])
async def update_status(
    background_tasks: BackgroundTasks,
    trip_id: str,
    status: TripStatusEnum,
    payload: Optional[
        AdditionalDetailsOnTripStatusChange
    ] = None,  # This payload can contain additional information like cancellation reason if the status is being updated to cancelled, or dispute reason if the status is being updated to dispute, etc. This will help us in maintaining a detailed trip status audit log for each trip which will be useful for analyzing the trip lifecycle and identifying any bottlenecks or issues in our operations.
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update the status of a trip."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin, RoleEnum.driver_admin]:
        raise CabboException(
            "You do not have permission to update trip status.", status_code=403
        )

    trip_schema, background_task = await update_trip_status(
        trip_id=trip_id,
        new_status=status,
        payload=payload,
        db=db,
        requestor=current_user,
        validate_time_window=True,
    )  # Adding time window validation to ensure that trip status updates are happening within the expected time windows based on the trip type and real-world conditions, which will help us maintain data integrity and provide a better experience for our customers and drivers by ensuring that the trip statuses are accurate and reflect the real-world status of the trips.
    if not trip_schema:
        raise CabboException("Failed to update trip status", status_code=500)
    if background_task:
        orchestrator = BackgroundTaskOrchestrator(background_tasks)
        orchestrator.add_task(
            background_task.fn,
            task_name=f"BackgroundTaskForTrip{trip_id}StatusUpdateTo{status.value}",
            **background_task.kwargs,
        )
    return {"message": f"Trip status updated to {status.value} successfully."}


# Assign driver to trip
@router.post("/{trip_id}/assign-driver/{driver_id}", tags=["Admin Trip Management"])
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
        trip=trip,
        driver=driver,
        db=db,
        requestor=current_user,
        attach_trip_relationships=True,
        validate_time_window=True,
    )  # Attaching trip relationships with customer details exposed, so that it can be used in the notification task to notify customer about driver assignment and trip confirmation

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


# Soft delete trip - only super_admin
@router.delete("/{trip_id}", tags=["Admin Trip Management"])
async def soft_delete_trip(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Soft delete a trip."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete trips.", status_code=403
        )
    return await delete_trip(trip_id=trip_id, db=db)


# Activate trip - only super_admin. This will be used to reactivate a trip that was previously soft deleted, in case it was deleted by mistake or if there is a need to restore the trip for any reason. This will help us maintain data integrity and provide flexibility in managing trips in our system.
@router.patch("/{trip_id}/activate", tags=["Admin Trip Management"])
async def enable_trip(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Activate a previously soft deleted trip."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to activate trips.", status_code=403
        )
    return await activate_trip(trip_id=trip_id, db=db)


# Get price breakdown for a trip by trip_id - this will be used by super_admin, finance_admin, and customer_admin to view the price breakdown for a particular trip, which can help them in analyzing the fare components and understanding the pricing structure of the trips in our system, and also to resolve any pricing related disputes or issues that may arise.
@router.get("/{trip_id}/price-breakdown", tags=["Admin Trip Management"])
async def get_price_breakdown(
    trip_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get price breakdown for a trip by trip_id."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.finance_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view trip price breakdown.",
            status_code=403,
        )
    trip = await async_get_trip_by_id(trip_id, db)
    if trip is None:
        raise CabboException("Trip not found", status_code=404)
    return trip.price_breakdown


# Include trip_reviews router for admin to view trip reviews by driver and by customer

router.include_router(
    reviews.router, prefix="/trip-reviews", tags=["Admin Trip Reviews"]
)
router.include_router(refunds.router, prefix="/refunds", tags=["Admin Trip Refunds"])

router.include_router(dispute.router, prefix="/disputes", tags=["Admin Trip Disputes"])
