from fastapi import APIRouter, Depends
from core.exceptions import CabboException
from core.security import validate_customer_token
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
from models.trip.trip_schema import TripUpdateRequestSchema
from services.trips.trip_service import (
    async_get_trip_by_booking_id_customer_id,
    async_get_trips_by_customer_id,
    group_by_trip_status,
    serialize_trip,
    serialize_trips,
    update_non_cost_impacting_trip_fields,
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


# Get price breakdown for a trip by booking_id - this will be used by frontend to fetch the price breakdown details for a trip after the booking is confirmed, so that we can show the price breakdown to the customer in the trip details page. This endpoint will validate the JWT token to ensure that only authenticated customers can access their trip price breakdown details securely.
@router.get(
    "/{booking_id}/price-breakdown",
    response_model=dict,
)
async def get_price_breakdown_by_booking_id(
    booking_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: Customer = Depends(validate_customer_token),
):
    """Get price breakdown for a trip by booking_id."""

    trip = await async_get_trip_by_booking_id_customer_id(
        booking_id, current_user.id, db
    )

    if trip is None:
        raise CabboException("Trip booking not found", status_code=404)

    price_breakdown = trip.price_breakdown
    if price_breakdown is None:
        raise CabboException("Price breakdown not found for the trip", status_code=404)

    return price_breakdown


# Update trip details by booking_id and customer_id - this will be used by frontend to update the trip details for a trip after the booking is confirmed, so that we can allow customers to update their trip details which are non-cost impacting. This endpoint will validate the JWT token to ensure that only authenticated customers can update their trip details securely.
@router.patch(
    "/{booking_id}",
    response_model=dict,
)
async def update_trip_details_by_booking_id_and_customer_id(
    booking_id: str,
    payload: TripUpdateRequestSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: Customer = Depends(validate_customer_token),
):
    """Update trip details by booking_id and customer_id."""

    trip = await async_get_trip_by_booking_id_customer_id(
        booking_id, current_user.id, db
    )

    if trip is None:
        raise CabboException("Trip booking not found", status_code=404)

    # Update the trip details based on the fields provided in the request
    updated = await update_non_cost_impacting_trip_fields(
        trip=trip, payload=payload, db=db, validate_status=True
    )
    if not updated:
        raise CabboException("Failed to update trip details", status_code=500)
    return {"message": "Trip details updated successfully"}


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
