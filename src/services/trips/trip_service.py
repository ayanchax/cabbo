from datetime import datetime, timedelta, timezone
import json
from typing import Union

from core.exceptions import CabboException
from core.security import RoleEnum, verify_hash
from core.store import ConfigStore
from core.trip_constants import TRIP_MESSAGES
from core.trip_helpers import attach_relationships_to_trip, generate_trip_field_dictionary, get_trip_type_id_by_trip_type
from models.common import AppBackgroundTask
from models.customer.customer_schema import CustomerRead
from models.customer.passenger_schema import  PassengerRequest
from models.driver.driver_schema import DriverReadSchema
from models.pricing.pricing_schema import (
    TripPackageConfigSchema,
)
from models.trip.temp_trip_orm import TempTrip
from models.trip.trip_enums import (
    CancellationSubStatusEnum,
    CarTypeEnum,
    FuelTypeEnum,
    TripStatusEnum,
    TripTypeEnum,
)
from models.trip.trip_orm import Trip, TripPackageConfig, TripTypeMaster
from models.trip.trip_schema import (
    AdditionalDetailsOnTripStatusChange,
    TripBookRequest,
    TripDetailSchema,
    TripDetails,
    TripSearchRequest,
    TripTypeSchema,
)
from sqlalchemy.orm import Session

from models.user.user_orm import User
from services.audit_trail_service import a_log_trip_audit
from services.driver_service import add_driver_earning_record, toggle_availability_of_driver
from services.passenger_service import (
    get_passenger_id_from_preferences,
    populate_passenger_details,
    validate_passenger_id,
)
from services.pricing_service import (
    get_driver_allowance,
    get_parking,
    get_tolls,
)
from services.refund_service import refund_advance_payment_to_customer
from services.validation_service import validate_serviceable_area, validate_trip_type
from utils.utility import remove_none_recursive, validate_date_time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

def serialize_trip(trip:Trip, expose_customer_details: bool = False):
    trip_dict = trip.__dict__.copy()  # Convert ORM object to a dictionary
    if trip.driver:  # Serialize the driver if it exists
            driver_data = DriverReadSchema.model_validate(trip.driver).model_dump()
            trip_dict["driver"] = driver_data
            trip_dict.pop("driver_id", None)
    else:
            trip_dict["driver"] = None
    if trip.trip_type_master:  # Serialize the trip type if it exists
            trip_type_data = TripTypeSchema.model_validate(trip.trip_type_master).model_dump()
            trip_dict["trip_type"] = trip_type_data
            trip_dict.pop("trip_type_id", None)
            trip_dict.pop("trip_type_master", None)
    else:
            trip_dict["trip_type"] = None
    if trip.package:  # Serialize the package if it exists
            package_data = TripPackageConfigSchema.model_validate(trip.package).model_dump()
            trip_dict["package"] = package_data
            trip_dict.pop("package_id", None)
    else:
            trip_dict["package"] = None
    if trip.passenger:  # Serialize the passenger if it exists
            passenger_data = PassengerRequest.model_validate(trip.passenger).model_dump()
            trip_dict["passenger"] = passenger_data
            trip_dict.pop("passenger_id", None)
    else:
            trip_dict["passenger"] = None

    if expose_customer_details:
         if trip.customer:
            customer_data = CustomerRead.model_validate(trip.customer).model_dump()
            trip_dict["customer"] = customer_data
            trip_dict.pop("creator_id", None)
            trip_dict.pop("creator_type", None)
         else:
            trip_dict["customer"] = None

    #Remove SQLAlchemy instance state which is not serializable and can cause issues during response serialization
    trip_dict.pop("_sa_instance_state", None)
    trip_details = TripDetailSchema.model_validate(trip_dict).model_dump(exclude_none=True)
    return remove_none_recursive(trip_details)


def _get_trip_type_by_trip_type_id(trip_type_id: str, db: Session) -> TripTypeEnum:
    """
    Retrieves the trip type from the database based on the provided trip type ID.
    Args:
        trip_type_id (str): The ID of the trip type to retrieve.
        db (Session): The database session for ORM operations.
    Returns:
        TripTypeEnum: The trip type corresponding to the provided ID.
    Raises:
        CabboException: If the trip type ID is not found in the database.
    """
    trip_type_obj = (
        db.query(TripTypeMaster).filter(TripTypeMaster.id == trip_type_id).first()
    )
    if not trip_type_obj:
        raise CabboException(
            f"Trip type with ID {trip_type_id} not found", status_code=404
        )
    return TripTypeEnum(trip_type_obj.trip_type)



def _get_total_num_luggages(booking_request: TripBookRequest) -> int:
    """
    Calculates the total number of luggages based on the booking request.
    Args:
        booking_request (TripBookRequest): The trip booking request containing luggage details.
    Returns:
        int: The total number of luggages.
    """
    return (
        booking_request.preferences.num_large_suitcases
        + booking_request.preferences.num_carryons
        + booking_request.preferences.num_backpacks
        + booking_request.preferences.num_other_bags
    )


def _retrieve_trip_package_by_id(
    package_id: str,
    db: Session,
    fallback_duration: int = 4,
    fallback_km: int = 40,
    fallback_label: str = "4Hours / 40KM",
):
    if not package_id:
        return TripPackageConfigSchema(
            included_hours=fallback_duration,
            included_km=fallback_km,
            package_label=fallback_label,
        )
    package = (
        db.query(TripPackageConfig).filter(TripPackageConfig.id == package_id).first()
    )
    if not package:
        return TripPackageConfigSchema(
            included_hours=fallback_duration,
            included_km=fallback_km,
            package_label=fallback_label,
        )
    package_schema = TripPackageConfigSchema.model_validate(package)
    return (
        package_schema
        if package_schema.included_hours and package_schema.included_hours > 0
        else TripPackageConfigSchema(
            included_hours=fallback_duration,
            included_km=fallback_km,
            package_label=fallback_label,
        )
    )


def _calculate_expected_trip_end_datetime(
    trip_type: TripTypeEnum,
    start_date: datetime,
    end_date: datetime,
    db: Session,
    package_id: str = None,
) -> datetime:
    """
    Calculates the expected end datetime for a trip based on the trip type, start date, end date, and package ID.
    Args:
        trip_type (TripTypeEnum): The type of trip (local, outstation, airport).
        start_date (datetime): The start date of the trip.
        end_date (datetime): The end date of the trip.
        package_id (str): The package ID if applicable.
    Returns:
        datetime: The expected end datetime for the trip.
    """
    if trip_type == TripTypeEnum.local:
        # For local trips, retrieve the package duration if available, otherwise default to 6 hours
        if package_id:
            package = _retrieve_trip_package_by_id(package_id=package_id, db=db)
            if package and package.included_hours:
                return start_date + timedelta(hours=package.included_hours)
        return start_date + timedelta(hours=4)  # Default to 4 hours for local trips

    elif trip_type == TripTypeEnum.outstation:
        # For outstation trips, use the provided end date
        return end_date

    elif trip_type in [TripTypeEnum.airport_pickup, TripTypeEnum.airport_drop]:
        # For airport trips, we can assume a short duration
        return start_date + timedelta(hours=1)  # Default to 1 hour for airport trips
    else:
        raise CabboException(
            f"Trip type {trip_type} is not supported for expected end datetime calculation",
            status_code=501,
        )


def get_trip_messages(status: Union[str, TripStatusEnum]):
    status = status.value if isinstance(status, TripStatusEnum) else status
    return TRIP_MESSAGES.get(status, {})


def _set_default_preferences(search_in: TripSearchRequest):
    """
    Ensures all required trip search preferences have sensible defaults.

    - Sets 'preferred_car_type' to CarTypeEnum.sedan if not provided.
    - Sets 'preferred_fuel_type' to FuelTypeEnum.diesel if not provided.
    - Ensures at least one adult is present (defaults to 1 if missing or < 1).
    - Ensures number of children is not negative (defaults to 0 if missing or < 0).

    Args:
        search_in (TripSearchRequest): The trip search request object to populate defaults for.
    """
    if not search_in.preferred_car_type:
        search_in.preferred_car_type = CarTypeEnum.sedan
    if not search_in.preferred_fuel_type:
        search_in.preferred_fuel_type = FuelTypeEnum.diesel
    if search_in.num_adults < 1 or search_in.num_adults is None:
        search_in.num_adults = 1  # Ensure at least one adult is present
    if search_in.num_children < 0 or search_in.num_children is None:
        search_in.num_children = 0

def verify_trip_hash(booking_request: TripBookRequest):
    if not hasattr(booking_request, "option"):
        raise CabboException(
            "Invalid booking request, option is required", status_code=400
        )

    if not booking_request.option or not hasattr(booking_request.option, "hash"):
        raise CabboException(
            "Invalid booking request, option hash is required", status_code=400
        )
    if not booking_request.preferences:
        raise CabboException(
            "Invalid booking request, preferences are required", status_code=400
        )
    # Validate the trip option hash
    option_dict, preference_dict = generate_trip_field_dictionary(
        search_in=booking_request.preferences,
        car_type=booking_request.option.car_type,
        fuel_type=booking_request.option.fuel_type,
        option=booking_request.option,
    )
    payload = json.dumps(
        {"option": option_dict, "preferences": preference_dict}, sort_keys=True
    )

    if not verify_hash(
        payload=payload,
        client_hash=booking_request.option.hash,
    ):
        raise CabboException(
            "Invalid booking request, option hash is not valid", status_code=400
        )


def validate_trip_search(
    search_in: TripSearchRequest, requestor: str, db: Session, config_store: ConfigStore
):

    # Validate passenger ID if provided
    validate_passenger_id(search_in, requestor, db)

    # Ensure all required trip search preferences have sensible defaults
    _set_default_preferences(search_in)

    # Enforce serviceable area boundaries
    validate_serviceable_area(search_in=search_in, config_store=config_store, db=db)

    trip_type = search_in.trip_type
    # Validate trip type
    validate_trip_type(trip_type, config_store=config_store)


def delete_temp_trip(requestor: str, db: Session):
    """
    Deletes all temporary trip details for the given requestor.
    We delete all temporary trip records for the requestor to ensure no stale temporary data remains in the system.
    Args:
        requestor (str): The user or system initiating the deletion.
        db (Session): The database session for ORM operations.
    """
    try:
        # Delete all temporary trip records for the requestor
        db.query(TempTrip).filter(TempTrip.creator_id == requestor).delete()
        db.commit()
        print(f"Temporary trip details deleted for requestor: {requestor}")
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Failed to delete temporary trip details: {str(e)}", status_code=500
        )


def create_temporary_trip(
    booking_request: TripBookRequest, requestor: str, db: Session
) -> TempTrip:
    """

    Creates a temporary trip record in the database based on the booking request.
    This function validates the booking request, calculates necessary fields, and stores the trip details.
    Args:
        booking_request (TripBookRequest): The trip booking request containing preferences and options.
        requestor (str): The user or system initiating the trip creation.
        db (Session): The database session for ORM operations.
    Returns:
        TempTrip: The created temporary trip record.
    Raises:
        CabboException: If the booking request is invalid or if any database operation fails.
    """
    trip_type_id = get_trip_type_id_by_trip_type(
        booking_request.preferences.trip_type, db=db
    )
    validated_start_date = validate_date_time(
        date_time=booking_request.preferences.start_date
    )

    validated_end_date = None
    if booking_request.preferences.end_date:
        validated_end_date = validate_date_time(
            date_time=booking_request.preferences.end_date
        )

    json_hops = (
        [hop.model_dump() for hop in booking_request.preferences.hops]
        if booking_request.preferences.hops
        else None
    )
    temp_trip = TempTrip(
        creator_id=requestor,
        trip_type_id=trip_type_id,
        origin=booking_request.preferences.origin.model_dump(),
        destination=booking_request.preferences.destination.model_dump(),
        hops=json_hops,
        is_interstate=(
            booking_request.metadata.is_interstate
            if booking_request.preferences.trip_type == TripTypeEnum.outstation
            else False
        ),
        is_round_trip=booking_request.metadata.is_round_trip if hasattr(booking_request.metadata, "is_round_trip") else False,
        total_unique_states=(
            booking_request.metadata.total_unique_states
            if booking_request.preferences.trip_type == TripTypeEnum.outstation
            else None
        ),
        unique_states=(
            booking_request.metadata.unique_states
            if booking_request.preferences.trip_type == TripTypeEnum.outstation
            else None
        ),
        package_id=(
            booking_request.preferences.package_id
            if booking_request.preferences.trip_type == TripTypeEnum.local
            and booking_request.preferences.package_id
            else None
        ),
        package_label=(
            booking_request.option.package if booking_request.option.package else None
        ),
        package_label_short=(
            booking_request.option.package_short_label
            if booking_request.option.package_short_label
            else None
        ),
        start_datetime=validated_start_date,
        end_datetime=validated_end_date,
        expected_end_datetime=_calculate_expected_trip_end_datetime(
            booking_request.preferences.trip_type,
            validated_start_date,
            validated_end_date,
            db,
            booking_request.preferences.package_id,
        ),
        total_days=(
            booking_request.metadata.total_trip_days
            if hasattr(booking_request.metadata, "total_trip_days")
            else None
        ),
        included_kms= booking_request.metadata.included_kms if hasattr(booking_request.metadata, "included_kms") else None,
        num_adults=booking_request.preferences.num_adults,
        num_children=booking_request.preferences.num_children,
        num_passengers=booking_request.preferences.num_adults
        + booking_request.preferences.num_children,
        num_large_suitcases=booking_request.preferences.num_large_suitcases,
        num_carryons=booking_request.preferences.num_carryons,
        num_backpacks=booking_request.preferences.num_backpacks,
        num_other_bags=booking_request.preferences.num_other_bags,
        num_luggages=_get_total_num_luggages(booking_request=booking_request),
        preferred_car_type=booking_request.preferences.preferred_car_type,
        preferred_fuel_type=booking_request.preferences.preferred_fuel_type,
        in_car_amenities=(
            booking_request.metadata.in_car_amenities.model_dump()
            if  booking_request.metadata.in_car_amenities
            else None
        ),
        price_breakdown=(
            booking_request.option.price_breakdown.model_dump()
            if booking_request.option.price_breakdown
            else None
        ),
        overages=(
            booking_request.option.overages.model_dump()
            if booking_request.option.overages
            else None
        ),
        base_fare=booking_request.option.price_breakdown.base_fare,
        driver_allowance=(
            get_driver_allowance(option=booking_request.option)
            if booking_request.preferences.trip_type
            in [TripTypeEnum.outstation, TripTypeEnum.local]
            else 0.0
        ),
        tolls=get_tolls(booking_request=booking_request),
        parking=get_parking(booking_request=booking_request),
        permit_fee=(
            booking_request.option.price_breakdown.permit_fee
            if booking_request.metadata.is_interstate
            and booking_request.option.price_breakdown.permit_fee
            else 0.0
        ),
        platform_fee=(
            booking_request.option.price_breakdown.platform_fee
            if booking_request.option.price_breakdown.platform_fee
            else 0.0
        ),
        final_price=booking_request.option.total_price,
        final_display_price=(
            booking_request.option.total_price
            - booking_request.option.price_breakdown.platform_fee
        ),
        inclusions=(
            booking_request.metadata.inclusions
            if booking_request.metadata.inclusions
            else None
        ),
        exclusions=(
            booking_request.metadata.exclusions
            if booking_request.metadata.exclusions
            else None
        ),
        flight_number=(
            booking_request.preferences.flight_number
            if booking_request.preferences.flight_number
            else None
        ),
        terminal_number=(
            booking_request.preferences.terminal_number
            if booking_request.preferences.terminal_number
            else None
        ),
        toll_road_preferred=(
            booking_request.preferences.toll_road_preferred
            if booking_request.preferences.toll_road_preferred
            else False
        ),
        placard_required=(
            booking_request.preferences.placard_required
            if booking_request.preferences.placard_required
            else False
        ),
        placard_name=(
            booking_request.preferences.placard_name
            if booking_request.preferences.placard_name
            else None
        ),
        estimated_km=(
            booking_request.metadata.estimated_km
            if booking_request.metadata.estimated_km
            else 0.0
        ),
        indicative_overage_warning=(
            booking_request.option.overages.indicative_overage_warning
            if booking_request.option.overages.indicative_overage_warning
            else None
        ),
        alternate_customer_phone=None,
        passenger_id=get_passenger_id_from_preferences(
            preferences=booking_request.preferences
        ),
        hash=(
            booking_request.option.hash
            if hasattr(booking_request.option, "hash")
            else None
        ),
    )
    try:
        db.add(temp_trip)
        db.commit()
        db.refresh(temp_trip)
        print(f"Temporary trip created for requestor: {requestor}")
        return temp_trip
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Failed to create temporary trip: {str(e)}", status_code=500
        )


def populate_trip_schema(trip: Union[Trip, TempTrip], db: Session) -> TripDetails:
    trip_schema = TripDetails.model_validate(
        trip
    )  # Convert Trip object to TripDetail schema
    trip_schema.trip_type = _get_trip_type_by_trip_type_id(
        trip_type_id=trip.trip_type_id, db=db
    )

    passenger = populate_passenger_details(passenger_id=trip.passenger_id, db=db)
    if passenger:
        trip_schema.passenger = passenger
    result = trip_schema.model_dump(
        exclude_none=True
    )  # Return the trip schema as a dictionary excluding None values
    return remove_none_recursive(result)


def get_trip_by_id(trip_id: str, db: Session) -> Trip:
    """Retrieve a trip by its ID."""
    return db.query(Trip).filter(Trip.id == trip_id).first()

async def async_get_trip_by_id(trip_id: str, db: AsyncSession, expose_customer_details: bool = False) -> Trip:
    """Asynchronously retrieve a trip by its ID."""
    query = select(Trip).filter(Trip.id == trip_id)
    result = await db.execute(query)
    trip_result = result.scalars().first()
    if trip_result:
        await attach_relationships_to_trip(trip_result, db, expose_customer_details=expose_customer_details)
    return trip_result

 
async def async_get_trip_by_booking_id(booking_id: str, db: AsyncSession) -> Trip:
    """Asynchronously retrieve a trip by its booking ID."""
    result = await db.execute(select(Trip).filter(Trip.booking_id == booking_id))
    trip_result = result.scalars().first()
    if trip_result:
        await attach_relationships_to_trip(trip_result, db)
    return trip_result

async def async_get_all_trips(db: AsyncSession) -> list[Trip]:
    """Asynchronously retrieve all trips."""
    result = await db.execute(select(Trip))
    all= result.scalars().all()
    for trip in all:
        await attach_relationships_to_trip(trip, db)
    return all

async def async_get_trips_by_driver_id(driver_id: str, db: AsyncSession) -> list[Trip]:
    """Asynchronously retrieve trips by driver ID."""
    query = select(Trip).filter(Trip.driver_id == driver_id)
    result = await db.execute(query)
    trips = result.scalars().all()
    if not trips:
        return []
    for trip in trips:
        await attach_relationships_to_trip(trip, db)
    return trips

def serialize_trips(trips: list[Trip], expose_customer_details: bool = False) -> list:
    serialized_trips = []
    for trip in trips:
        serialized_trips.append(serialize_trip(trip, expose_customer_details=expose_customer_details))
    return serialized_trips

async def async_get_trips_by_customer_id(customer_id: str, db: AsyncSession, expose_customer_details: bool = False) -> list[Trip]:
    """Asynchronously retrieve trips by customer ID."""
    result = await db.execute(select(Trip).filter(Trip.creator_id == customer_id, Trip.creator_type== RoleEnum.customer.value))
    trips = result.scalars().all()
    if not trips:
        return []
    for trip in trips:
        await attach_relationships_to_trip(trip, db, expose_customer_details=expose_customer_details)
    return trips

def group_by_trip_status(trips: list[dict], validate_by_tz: bool = False) -> dict:
        if validate_by_tz:
            print("Grouping trips by status with timezone validation")
            return _group_by_trip_status_with_timezone_validation(trips)
        print("Grouping trips by status without timezone validation")
        upcoming_trips = [trip for trip in trips if trip.get("status") == TripStatusEnum.confirmed.value]
        ongoing_trips = [trip for trip in trips if trip.get("status") == TripStatusEnum.ongoing.value]
        past_trips = [trip for trip in trips if trip.get("status") in [TripStatusEnum.completed.value, TripStatusEnum.cancelled.value]]
        return {"upcoming": upcoming_trips, "ongoing": ongoing_trips, "past": past_trips}




def _group_by_trip_status_with_timezone_validation(trips: list[dict]) -> dict:
    current_datetime = datetime.now(timezone.utc)
    upcoming_trips = []
    ongoing_trips = []
    past_trips = []

    for trip in trips:
        trip_status = trip.get("status")
        trip_type = trip.get("trip_type").get("trip_type") if trip.get("trip_type") else None
        start_datetime = trip.get("start_datetime")
        expected_end_datetime = trip.get("expected_end_datetime")

        # Ensure start_datetime and expected_end_datetime are timezone-aware
        if start_datetime and start_datetime.tzinfo is None:
            start_datetime = start_datetime.replace(tzinfo=timezone.utc)
        if expected_end_datetime and expected_end_datetime.tzinfo is None:
            expected_end_datetime = expected_end_datetime.replace(tzinfo=timezone.utc)

        # Airport Pickup, Drop, Rental Logic (1 day buffer for ongoing trips to account for delays and real-world conditions)
        if trip_type in [TripTypeEnum.airport_pickup.value, TripTypeEnum.airport_drop.value, TripTypeEnum.local.value]:
            if trip_status == TripStatusEnum.confirmed.value and start_datetime > current_datetime:
                upcoming_trips.append(trip)
            elif trip_status == TripStatusEnum.ongoing.value and start_datetime <= current_datetime and start_datetime >= (current_datetime - timedelta(hours=24)):
                ongoing_trips.append(trip)
            elif trip_status in [TripStatusEnum.completed.value, TripStatusEnum.cancelled.value] and start_datetime <= current_datetime:
                past_trips.append(trip)

        # Outstation Logic(strictly based on start and expected end datetime to account for real-world conditions like delays, early arrivals, etc.)
        elif trip_type == TripTypeEnum.outstation.value:
            if trip_status == TripStatusEnum.confirmed.value and start_datetime > current_datetime and expected_end_datetime > current_datetime:
                upcoming_trips.append(trip)
            elif trip_status == TripStatusEnum.ongoing.value and start_datetime <= current_datetime and expected_end_datetime >= current_datetime:
                ongoing_trips.append(trip)
            elif trip_status in [TripStatusEnum.completed.value, TripStatusEnum.cancelled.value] and start_datetime <= current_datetime and expected_end_datetime <= current_datetime:
                past_trips.append(trip)

    return {"upcoming": upcoming_trips, "ongoing": ongoing_trips, "past": past_trips}

async def update_trip_status(trip_id:str, db:AsyncSession, new_status: TripStatusEnum, requestor:User, payload: AdditionalDetailsOnTripStatusChange = None):
    trip = await async_get_trip_by_id(trip_id, db, expose_customer_details=True)
    if trip is None:
        raise CabboException("Trip not found", status_code=404)
    
    allowed_status_transitions = {
        TripStatusEnum.confirmed: [TripStatusEnum.ongoing, TripStatusEnum.cancelled],
        TripStatusEnum.ongoing: [TripStatusEnum.completed],
        TripStatusEnum.completed: [TripStatusEnum.dispute],
        TripStatusEnum.cancelled: [],
    }
    # Out of confirmed, ongoing, completed, canceled and dispute, a trip gets confirmed only from the #booking_service.py confirm_trip_booking() method.
    if new_status not in allowed_status_transitions.get(TripStatusEnum(trip.status), []):     
        raise CabboException(
            f"Invalid status transition from {trip.status} to {new_status.value}.", status_code=400
        )
    trip_schema: TripDetailSchema = None
    background_task: AppBackgroundTask = None
    try:
        #Ongoing status indicates the trip has started, so we set the actual start datetime when the trip starts. For other status updates, we only update the status without modifying the start datetime.
        if new_status ==TripStatusEnum.ongoing: #which means existing trip is in confirmed state.
            if trip.driver_id is None:
                raise CabboException("Cannot start trip without an assigned driver", status_code=400)
            
            #Update start datetime - The driver_admin can get the actual start datetime from the driver when they start the trip in the driver app, if not provided we will set the start datetime as current datetime in UTC timezone.            trip.start_datetime = payload.start_datetime if payload and payload.start_datetime else datetime.now(timezone.utc) #Set the actual start datetime when trip starts
            trip.start_datetime = payload.start_datetime if payload and payload.start_datetime else datetime.now(timezone.utc) #Set the actual start datetime when trip starts
            
            #Update status
            trip.status = new_status.value
            
            #Log audit trail for trip start
            await a_log_trip_audit(
                trip_id=trip.id,
                status=new_status,
                committer_id=requestor.id,
                reason=f"Trip started. {payload.reason if payload and payload.reason else ''}",
                changed_by=requestor.role,
                db=db,
                commit=False,  # Defer commit to batch with trip update
            )
            await db.flush()  # Flush to ensure the start_datetime and status update is saved before any further operations 
            await db.commit()
            await db.refresh(trip)
            trip_schema = TripDetailSchema.model_validate(trip)
            
        # Completed status indicates the trip has ended, so we set the actual end datetime when the trip is completed and also update the balance payment to zero and record any extra payments to driver at trip completion and free up the driver for new trips. For other status updates, we only update the status without modifying the end datetime, balance payment and extra payment details.
        elif new_status ==TripStatusEnum.completed: #which means existing trip is in ongoing state.
            if trip.driver_id is None:
                raise CabboException("Cannot complete trip without an assigned driver", status_code=400)
            
            extra= payload.extra_payment_to_driver.model_dump(exclude_unset=True, exclude_none=True) if payload and payload.extra_payment_to_driver else None
            
            #Update end datetime with the actual end datetime when trip is completed. The driver_admin can get the actual end datetime from the driver, if not provided we will set the end datetime as current datetime in UTC timezone.
            trip.end_datetime = payload.end_datetime if payload and payload.end_datetime else datetime.now(timezone.utc) #Set the actual end datetime when trip is completed
            
            #Update status
            trip.status = new_status.value
            
            # Set balance_payment zero, because a completed trip can only be marked as complete once the driver_admin confirms the trip completion from the driver (and gather additional details like actual end datetime, ensures remaining fare was paid to driver etc.) 
            # and at that point we can be sure about the final price and there should not be any balance payment pending from customer. In case of any change in price after trip completion, we will not handle that because all remaining payments are paid directly to driver and we will not be handling any post trip completion price adjustments in the system for now.
            # In case of disputes where customer did not pay the driver the remaining amount or any extra charges, then we will mark the trip as dispute and try to resolve it between the two parties.
            # Our driver will not over charge the customer at the end of the trip, customer needs to pay only what is showing as remaining in the app (plus any additional charges of tolls, paid parking, additional mileage etc. subject to proof/reciepts shown by driver to customer.)
            
            #Update balance payment to 0.0
            trip.balance_payment = 0.0

            #Update extra payments to driver at trip completion, if any.
            # We store the breakdown of any extra amount received by driver such as paid parking, tolls, overage payment and any tips given to the driver. We collect this information as part of the trip completion process in the driver app and store it in the trip record for future reference in case of any disputes or queries from either party regarding the final amount paid to driver.
            trip.extra_payment_to_driver=extra

            #Free up the driver
            await toggle_availability_of_driver(driver_id=trip.driver_id, db=db, make_available=True, commit=False)
            
            #Log audit trail for trip completion
            await a_log_trip_audit(
                trip_id=trip.id,
                status=new_status,
                committer_id=requestor.id,
                reason=f"Trip completed. {payload.reason if payload and payload.reason else ''}",
                changed_by=requestor.role,
                db=db,
                commit=False,  # Defer commit to batch with trip update
            )
            await db.flush()  # Flush to ensure the end_datetime, status update, balance payment update and extra payment details are saved before any further operations
            await db.commit()
            await db.refresh(trip)
            
            # Add a record to DriverEarning for the amount paid to driver - Background Task
            # Delegating the task of adding driver earning record to background task because it is a secondary work and also to ensure that the main flow of trip completion and marking driver available is not affected by any potential issues in adding driver earning record and also to improve the response time for trip completion API. 
            trip_schema = TripDetailSchema.model_validate(trip)
            background_task = AppBackgroundTask(fn=add_driver_earning_record, kwargs={
                "trip": trip_schema,
                "additional_info":payload,
                "db": db,
                "requestor": requestor.id,
                "silently_fail": True,  # We want to ensure that even if adding driver earning record fails for some reason, it should not affect the main flow of trip completion and marking driver available. So we will silently fail any errors in the background task and log them for future reference.
            })

        elif new_status == TripStatusEnum.cancelled:
            # A canceled trip may or may not have an assigned driver, so we do not check for driver assignment before allowing cancellation. We allow cancellation of a trip without an assigned driver because sometimes customers may want to cancel a trip before a driver is assigned to avoid any inconvenience and also to allow them to book a new trip with correct details if they made any mistake in the initial booking.
            
            #Update status.
            trip.status = new_status.value

            if trip.driver_id:
                #Free up the driver if already assigned to the trip.
                await toggle_availability_of_driver(driver_id=trip.driver_id, db=db, make_available=True, commit=False)
            
            #Update cancelation time
            trip.cancelation_datetime = datetime.now(timezone.utc)
            cancelation_sub_status = CancellationSubStatusEnum.other
            if requestor.role == RoleEnum.customer:
                cancelation_sub_status = CancellationSubStatusEnum.customer_cancelled

            else:
                cancelation_sub_status=payload.cancellation_sub_status if payload and payload.cancellation_sub_status else CancellationSubStatusEnum.other
            
            #Log audit trail for trip cancellation
            await a_log_trip_audit(
                trip_id=trip.id,
                status=new_status,
                committer_id=requestor.id,
                reason=f"Trip cancelled. {payload.reason if payload and payload.reason else ''}",
                changed_by=requestor.role,
                cancellation_sub_status = cancelation_sub_status,
                db=db,
                commit=False,  # Defer commit to batch with trip update
            )
            await db.flush()  # Flush to ensure the status update and audit log is saved before any further operations 
            await db.commit()
            await db.refresh(trip)
            trip_schema = TripDetailSchema.model_validate(trip)
            
            background_task = AppBackgroundTask(fn=refund_advance_payment_to_customer, kwargs={
                    "trip": trip_schema,
                    "db": db,
                    "canceled_by_cabbo": cancelation_sub_status!=CancellationSubStatusEnum.customer_cancelled, # We will refund advance payment to customer only if the trip is canceled by cabbo or by driver or due to any other reason except customer cancellation, because if the customer is canceling the trip then they should be responsible for any cancellation charges and we should not refund the advance payment in that case or refund partially. But if the trip is canceled by cabbo or by driver or due to any other reason except customer cancellation, then we should refund the advance payment to customer because it is not the fault of customer and they should not be penalized for that.
                    "silently_fail": True,  # We want to ensure that even if refunding advance payment fails for some reason, it should not affect the main flow of trip cancellation and marking driver available. So we will silently fail any errors in the background task and log them for future reference.
                })


    except Exception as e:
        await db.rollback()
        raise CabboException(f"Failed to update trip status: {str(e)}", status_code=500)


    return trip_schema, background_task

