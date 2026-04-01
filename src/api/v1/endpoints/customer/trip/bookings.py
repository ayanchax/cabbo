from fastapi import APIRouter, Depends
from core.exceptions import CabboException
from core.security import validate_customer_token
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
from services.trips.trip_service import (
    async_get_trip_by_booking_id_customer_id,
    async_get_trips_by_customer_id,
    group_by_trip_status,
    serialize_trip,
    serialize_trips,
)
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


# View trip details by booking_id and customer_id.
@router.get("/{booking_id}")
async def view_trip_details_by_booking_id_and_customer_id(
    booking_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: Customer = Depends(validate_customer_token),
):
    """View trip details by booking_id and customer_id."""

    trip = await async_get_trip_by_booking_id_customer_id(
        booking_id, current_user.id, db
    )

    if trip is None:
        raise CabboException("Trip booking not found", status_code=404)
    serialized_trip = serialize_trip(trip)
    if "id" in serialized_trip:
        serialized_trip.pop(
            "id"
        )  # Remove internal trip ID from the response for security reasons
    return serialized_trip


# Get all trips for the authenticated customer
@router.get("/", response_model=dict)
async def list_trips_by_customer_id(
    db: AsyncSession = Depends(a_yield_mysql_session),
    customer: Customer = Depends(validate_customer_token),
):
    """List trips by customer_id."""

    trips = await async_get_trips_by_customer_id(
        customer_id=customer.id, db=db, expose_customer_details=True
    )
    if not trips:
        raise CabboException("No trips found for the customer", status_code=404)

    serialized_trips = serialize_trips(trips, expose_customer_details=True)

    # Remove id from each trip in the serialized_trips for security reasons
    for trip in serialized_trips:
        if "id" in trip:
            trip.pop("id")

    return group_by_trip_status(trips=serialized_trips, validate_by_tz=True)


# Get trips for the authenticated customer filtered by status
@router.get("/by/status/{status}", response_model=dict)
async def list_trips_by_customer_id_and_status(
    status: TripStatusEnum,
    db: AsyncSession = Depends(a_yield_mysql_session),
    customer: Customer = Depends(validate_customer_token),
):
    """List trips of customer by status."""

    trips = await async_get_trips_by_customer_id(
        customer.id, db, expose_customer_details=True
    )
    if not trips:
        raise CabboException("No trips found for the customer", status_code=404)

    serialized_trips = serialize_trips(trips, expose_customer_details=True)

    # Remove id from each trip in the serialized_trips for security reasons
    for trip in serialized_trips:
        if "id" in trip:
            trip.pop("id")
    filtered_trips = [
        trip for trip in serialized_trips if trip.get("status") == status.value
    ]

    if not filtered_trips:
        raise CabboException(
            f"No trips found for status: {status.value}", status_code=404
        )

    return group_by_trip_status(trips=filtered_trips, validate_by_tz=True)


# Get trips for the authenticated customer filtered by trip type
@router.get("/by/trip-type/{trip_type}", response_model=dict)
async def list_trips_by_customer_id_and_trip_type(
    trip_type: TripTypeEnum,
    db: AsyncSession = Depends(a_yield_mysql_session),
    customer: Customer = Depends(validate_customer_token),
):
    """List trips of customer by trip type."""

    trips = await async_get_trips_by_customer_id(
        customer.id, db, expose_customer_details=True
    )
    if not trips:
        raise CabboException("No trips found for the customer", status_code=404)

    serialized_trips = serialize_trips(trips, expose_customer_details=True)
    # Remove id from each trip in the serialized_trips for security reasons
    for trip in serialized_trips:
        if "id" in trip:
            trip.pop("id")
    filtered_trips = [
            trip
            for trip in serialized_trips
            if trip.get("trip_type", {}).get("trip_type") == trip_type.value
        ]

    if not filtered_trips:
        raise CabboException(
            f"No trips found for trip type: {trip_type.value}", status_code=404
        )
    return group_by_trip_status(trips=filtered_trips, validate_by_tz=True)
