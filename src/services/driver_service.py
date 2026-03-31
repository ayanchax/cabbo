from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import func
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.trip_helpers import attach_relationships_to_trip
from models.customer.customer_schema import CustomerReadWithProfilePicture
from models.driver.driver_orm import Driver, DriverEarning, TripRating
from models.driver.driver_schema import (
    DriverCreateSchema,
    DriverEarningSchema,
    DriverReadSchema,
    DriverReadWithProfilePicture,
    DriverUpdateSchema,
)
from core.security import ActiveInactiveStatusEnum, RoleEnum
import uuid

from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    AdditionalDetailsOnTripStatusChange,
    TripDetailSchema,
    TripSummarySchema,
)
from models.user.user_orm import User
from services.audit_trail_service import a_log_trip_audit
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select



def create_driver(
    payload: DriverCreateSchema,
    db: Session,
    created_by: RoleEnum = RoleEnum.driver_admin,
) -> Driver:
    """Create a new driver."""
    try:

        driver = Driver(
            id=str(uuid.uuid4()),
            name=payload.name,
            phone=payload.phone,
            email=payload.email,
            gender=payload.gender,
            dob=payload.dob,
            emergency_contact_name=payload.emergency_contact_name,
            emergency_contact_number=payload.emergency_contact_number,
            nationality=payload.nationality,
            religion=payload.religion,
            fuel_type=payload.fuel_type,
            cab_type=payload.cab_type,
            cab_model_and_make=payload.cab_model_and_make,
            cab_registration_number=payload.cab_registration_number,
            cab_amenities=(
                payload.cab_amenities.model_dump() if payload.cab_amenities else None
            ),
            payment_mode=payload.payment_mode,
            payment_phone_number=payload.payment_phone_number,
            bank_details=(
                payload.bank_details.model_dump() if payload.bank_details else None
            ),
            address=payload.address.model_dump() if payload.address else None,
            is_active=True,
            is_available=True,
            created_by=created_by,
        )
        db.add(driver)
        db.commit()
        db.refresh(driver)
        return driver
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error creating driver: {str(e)}", status_code=500, include_traceback=True
        )


def get_driver_by_id(driver_id: str, db: Session) -> Driver:
    """Retrieve a driver by their ID."""
    return db.query(Driver).filter(Driver.id == driver_id).first()


async def a_get_driver_by_id(driver_id: str, db: AsyncSession) -> Driver:
    """Retrieve a driver by their ID."""
    result = await db.execute(select(Driver).filter(Driver.id == driver_id))
    return result.scalars().first()


def get_driver_by_phone(phone: str, db: Session) -> Driver:
    """Retrieve a driver by their phone number."""
    return db.query(Driver).filter(Driver.phone == phone).first()


def get_driver_by_email(email: str, db: Session) -> Driver:
    """Retrieve a driver by their email address."""
    return db.query(Driver).filter(Driver.email == email).first()


def get_all_drivers(db: Session):
    """Retrieve all drivers."""
    return db.query(Driver).all()


def get_all_active_drivers(db: Session):
    """Retrieve all active drivers."""
    return db.query(Driver).filter(Driver.is_active == True).all()


def get_all_drivers_by_availability(is_available: bool, db: Session):
    """Retrieve all drivers by their availability status."""
    return db.query(Driver).filter(Driver.is_available == is_available).all()


def get_all_drivers_by_status(status: ActiveInactiveStatusEnum, db: Session):
    """Retrieve all drivers by their active status."""

    if status == ActiveInactiveStatusEnum.active:
        return get_all_active_drivers(db)
    elif status == ActiveInactiveStatusEnum.inactive:
        return get_all_inactive_drivers(db)
    else:
        raise CabboException(
            "Invalid status. Use 'active' or 'inactive'.", status_code=400
        )


def get_all_inactive_drivers(db: Session):
    """Retrieve all inactive drivers."""
    return db.query(Driver).filter(Driver.is_active == False).all()


def update_driver(driver_id: str, payload: DriverUpdateSchema, db: Session) -> Driver:
    """Update an existing driver's details."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    for field, value in payload.model_dump(exclude_unset=True).items():
        if hasattr(driver, field) and value is not None:
            setattr(driver, field, value)

    db.commit()
    db.refresh(driver)
    return driver


def delete_driver(driver_id: str, db: Session) -> bool:
    """Delete a driver by their ID."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    db.delete(driver)
    db.commit()
    return True


def activate_driver(driver_id: str, db: Session) -> Driver:
    """Activate a driver by their ID."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    driver.is_active = True
    db.commit()
    db.refresh(driver)
    return driver


def deactivate_driver(driver_id: str, db: Session) -> Driver:
    """Deactivate a driver by their ID."""
    driver = get_driver_by_id(driver_id, db)
    if not driver:
        raise CabboException("Driver not found", status_code=404)
    driver.is_active = False
    db.commit()
    db.refresh(driver)
    return driver


def update_driver_last_modified(driver: Driver, db: Session):
    try:
        driver.last_modified = datetime.now(timezone.utc)
        db.commit()
        db.refresh(driver)
    except Exception as e:
        db.rollback()
    return driver


async def assign_driver_to_trip(
    trip: Trip,
    driver: Driver,
    db: AsyncSession,
    requestor: User,
    attach_trip_relationships: bool = False,
    validate_time_window: bool = False,
):
    try:
        # Check Trip is in confirmed status
        if trip.status != TripStatusEnum.confirmed.value:
            raise CabboException(
                "Trip must be in confirmed status to assign a driver.", status_code=400
            )
        trip_type = (
            trip.trip_type_master.trip_type
            if hasattr(trip.trip_type_master, "trip_type")
            else None
        )
        if not trip_type:
            raise CabboException(
                "Trip type not found for the trip to assign driver.", status_code=400
            )
        start_datetime = None
        expected_end_datetime = None
        if trip.start_datetime.tzinfo is None:
            start_datetime = trip.start_datetime.replace(tzinfo=timezone.utc)

        if trip.expected_end_datetime and trip.expected_end_datetime.tzinfo is None:
            expected_end_datetime = trip.expected_end_datetime.replace(
                tzinfo=timezone.utc
            )
        if validate_time_window:
            # For airport drop, pickup and hourly rental trip types, block trips that happened in the past but somehow still have confirmed status. This is a bad data issue. Ideally this should not happen, but we are adding this check to prevent assigning drivers to such orphan trips which are in the past and should have been completed or cancelled but are still showing as confirmed due to some data issue.
            if trip_type in [
                TripTypeEnum.airport_drop,
                TripTypeEnum.airport_pickup,
                TripTypeEnum.local,
            ] and start_datetime < datetime.now(timezone.utc):
                raise CabboException(
                    "Cannot assign driver to a trip that is in the past.",
                    status_code=400,
                )
            # For outstation trips, disallow assigning driver if the start date time and the expected end date time both are in the past, as that means the trip is already completed but still showing as confirmed due to some data issue. This is to prevent assigning drivers to such orphan trips.
            if (
                trip_type == TripTypeEnum.outstation
                and start_datetime < datetime.now(timezone.utc)
                and expected_end_datetime < datetime.now(timezone.utc)
            ):
                raise CabboException(
                    "Cannot assign driver to a trip that is in the past.",
                    status_code=400,
                )
        # Check Trip has a valid creator_id
        if not trip.creator_id:
            raise CabboException(
                "Trip does not have a valid creator to assign a driver.",
                status_code=400,
            )
        # Check Trip creator is a customer
        if not trip.creator_type or trip.creator_type != RoleEnum.customer.value:
            raise CabboException(
                "Trip creator must be a customer to assign a driver.", status_code=400
            )
        # Check trip has a non-zero balance_payment, so that customer has paid advance and there is balance to be paid to driver
        if trip.balance_payment <= 0:
            raise CabboException(
                "Trip must have a non-zero balance payment to assign a driver.",
                status_code=400,
            )
        if trip.advance_payment <= 0:
            raise CabboException(
                "Trip must have a non-zero advance payment to assign a driver.",
                status_code=400,
            )
        # Check Driver is not already assigned to the trip
        if trip.driver_id == driver.id:
            raise CabboException(
                "Driver is already assigned to this trip.", status_code=400
            )

        # Free up the currently assigned driver (if any)
        if trip.driver_id:
            current_driver = await db.execute(
                select(Driver).where(
                    Driver.id == trip.driver_id, Driver.is_available == False
                )
            )
            current_driver = current_driver.scalars().first()
            if current_driver:
                current_driver.is_available = (
                    True  # Mark the current driver as available
                )
                db.add(current_driver)  # Add the updated driver back to the session

        # Check Driver is active
        if not driver.is_active:
            raise CabboException("Driver is not active.", status_code=400)

        # Check Driver is available
        if not driver.is_available:
            raise CabboException("Driver is not available.", status_code=400)

        # Check Driver has a valid phone number
        if not driver.phone or driver.phone.strip() == "":
            raise CabboException(
                "Driver does not have a valid phone number.", status_code=400
            )

        # When we have the driver app we will also check if the driver is kyc_verified or not.

        # Assign Driver to Trip
        # Once driver is assigned to trip, the trip status will still be confirmed until the driver admin marks the trip as ongoing after the driver informs the admin on trip start.
        # Since we have the driver_id assigned to a confirmed trip, we can easily find assigned trips for a driver without needing a sub status like 'assigned'. Moreover, we are logging this event in the trip audit log.
        # Later when we have the driver app, the driver can mark the trip as ongoing (post otp from customer) from the app which will update the trip status to ongoing. This will be done same way like Uber, Ola etc.
        trip.driver_id = driver.id
        # Update Driver availability to False
        driver.is_available = False

        await db.commit()
        await db.refresh(trip)
        await db.refresh(driver)
        await a_log_trip_audit(
            trip_id=trip.id,
            status=trip.status,
            committer_id=requestor.id,
            reason=f"Driver {driver.name} assigned to trip.",
            db=db,
        )  # Log the trip status audit entry
        if attach_trip_relationships:
            await attach_relationships_to_trip(
                trip, db, expose_customer_details=True
            )  # Expose customer details for access in notification task

        return trip, driver
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Error assigning driver to trip: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


async def _add_driver_earning_record(
    payload: DriverEarningSchema,
    db: AsyncSession,
    requestor: str,
    silently_fail: bool = False,
    commit: bool = True,
) -> DriverEarning | None:
    try:
        breakdown = (
            payload.extra_earnings_breakdown.model_dump(
                exclude_unset=True, exclude_none=True
            )
            if payload.extra_earnings_breakdown
            else None
        )
        driver_earning = DriverEarning(
            trip_id=payload.trip_id,
            driver_id=payload.driver_id,
            earnings=payload.base_earnings,
            extra_earnings=payload.extra_earnings,
            extra_earnings_breakdown=breakdown,
            total_earnings=payload.total_earnings,
            created_by=requestor,
        )
        db.add(driver_earning)
        await db.flush()  # Flush to get the ID of the new record if needed for logging or other purposes before commit
        if commit:
            await db.commit()
            await db.refresh(driver_earning)
        return driver_earning
    except Exception as e:
        await db.rollback()
        if silently_fail:
            print(f"Error adding driver earning record: {str(e)}")
            return None
        raise CabboException(
            f"Error adding driver earning record: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


async def toggle_availability_of_driver(
    driver_id: str, make_available: bool, db: AsyncSession, commit: bool = True
) -> Driver:
    try:
        driver = await a_get_driver_by_id(driver_id, db)
        if not driver:
            raise CabboException("Driver not found", status_code=404)
        driver.is_available = make_available
        await db.flush()  # Flush to apply the change before commit
        if commit:
            await db.commit()
            await db.refresh(driver)
        return driver
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Error updating driver availability: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


async def add_driver_earning_record(
    trip: TripDetailSchema,
    additional_info: AdditionalDetailsOnTripStatusChange,
    db: AsyncSession,
    requestor: str,
    commit: bool = True,
    silently_fail: bool = False,
):
    try:
        base_earnings = (
            (trip.final_price - trip.platform_fee)
            if trip.final_price
            and trip.platform_fee
            and trip.final_price > trip.platform_fee
            else 0.0
        )
        extra_earnings = (
            additional_info.extra_payment_to_driver.total_extra_payment
            if additional_info
            and additional_info.extra_payment_to_driver
            and additional_info.extra_payment_to_driver.total_extra_payment
            else 0.0
        )
        total_earnings = base_earnings + extra_earnings
        driver = trip.driver
        driver_schema = DriverReadSchema.model_validate(driver) if driver else None
        if not driver_schema:
            if silently_fail:
                print(
                    f"Driver not found for trip {trip.id} while adding driver earning record."
                )
                return None
            raise CabboException("Driver not found", status_code=404)

        # Delete existing driver earning record for this trip before adding a new one
        existing_record = await get_trip_earning_for_driver(
            trip_id=trip.id, driver_id=driver_schema.id, db=db
        )
        if existing_record:
            await delete_driver_earning(
                earning_id=existing_record.id, db=db, commit=commit, hard_delete=True
            )

        return await _add_driver_earning_record(
            payload=DriverEarningSchema(
                trip_id=trip.id,
                driver_id=driver_schema.id if driver_schema else None,
                base_earnings=base_earnings,
                extra_earnings=extra_earnings,
                total_earnings=total_earnings,
                extra_earnings_breakdown=(
                    additional_info.extra_payment_to_driver
                    if additional_info and additional_info.extra_payment_to_driver
                    else None
                ),
            ),
            db=db,
            requestor=requestor,
            silently_fail=silently_fail,  # We want to silently fail the driver earning record creation in case of any issues because we don't want to block the trip completion process for the driver. We can have a separate process to identify and fix any issues with driver earning records later without impacting the trip completion flow for drivers.
            commit=commit,
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        if silently_fail:
            print(f"Error in add_driver_earning_record: {str(e)}")
            return None
        raise CabboException(
            f"Error in add_driver_earning_record: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


async def get_trip_earning_for_driver(
    trip_id: str, driver_id: str, db: AsyncSession
) -> DriverEarning | None:
    try:
        result = await db.execute(
            select(DriverEarning).where(
                DriverEarning.trip_id == trip_id, DriverEarning.driver_id == driver_id
            )
        )
        return result.scalars().first()
    except Exception as e:
        print(
            f"Error fetching driver earning record for trip {trip_id} and driver {driver_id}: {str(e)}"
        )
        return None


async def has_driver_earning_record_for_trip(
    trip_id: str, driver_id: str, db: AsyncSession
) -> bool:
    try:
        result = await db.execute(
            select(DriverEarning).where(
                DriverEarning.trip_id == trip_id, DriverEarning.driver_id == driver_id
            )
        )
        record = result.scalars().first()
        return record is not None
    except Exception as e:
        print(
            f"Error checking driver earning record for trip {trip_id} and driver {driver_id}: {str(e)}"
        )
        return False


async def delete_driver_earning(
    earning_id: str, db: AsyncSession, commit=True, hard_delete=False
) -> bool:
    try:
        result = await db.execute(
            select(DriverEarning).where(
                DriverEarning.id == earning_id, DriverEarning.is_active == True
            )
        )
        earning_record = result.scalars().first()
        if not earning_record:
            return False
        if hard_delete:
            await db.delete(earning_record)
        else:
            earning_record.is_active = False  # Soft delete the earning record
        await db.flush()
        if commit:
            await db.commit()
        return True
    except Exception as e:
        await db.rollback()
        print(f"Error deleting driver earning record with id {earning_id}: {str(e)}")
        return False


async def calculate_average_rating_for_driver(
    driver_id: str,
    db: AsyncSession,
    exclude_flagged_ratings: bool = False,
    silently_fail: bool = False,
) -> Optional[float]:
    """
    Calculate the average rating for a driver based on all the trip ratings provided by customers.

    Args:
        driver_id (str): Unique identifier for the driver
        db (AsyncSession): Database session
        exclude_flagged_ratings (bool): A flag to indicate whether to exclude ratings that are flagged as inappropriate or fake from the average rating calculation for the driver to ensure that the average rating reflects genuine customer feedback and experience with the driver. Default is False.
        silently_fail (bool): A flag to indicate whether to silently fail if the driver is not found. Default is False.
    Returns:
        Optional[float]: The average rating for the driver rounded to 2 decimal places. Returns
        None if there are no ratings for the driver.
    """
    try:
        print(
            f"Calculating average rating for driver with id {driver_id} with exclude_flagged_ratings={exclude_flagged_ratings} and silently_fail={silently_fail}"
        )
        query = select(func.avg(TripRating.rating)).where(
            TripRating.driver_id == driver_id
        )
        if exclude_flagged_ratings:
            # Exclude ratings that are flagged as inappropriate or fake from the average rating calculation for the driver to ensure that the average rating reflects genuine customer feedback and experience with the driver.
            query = query.where(TripRating.is_flagged == False) #pick up all ratings which are not flagged as inappropriate or fake for the average rating calculation for the driver

        result = await db.execute(query)
        average_rating = result.scalar()
        return round(average_rating, 2) if average_rating is not None else None
    except Exception as e:
        if silently_fail:
            print(
                f"Failed to calculate average rating for the driver with id {driver_id}: {str(e)}"
            )
            return None
        raise CabboException(
            f"Failed to calculate average rating for the driver: {str(e)}",
            status_code=500,
        )


async def get_average_rating_by_driver_id(
    driver_id: str,
    db: AsyncSession,
) -> float:

    try:
        driver = await a_get_driver_by_id(driver_id=driver_id, db=db)
        if not driver:
            raise CabboException(
                "Driver not found for the given driver_id", status_code=404
            )
        average_rating = driver.avg_rating
        if average_rating is None:
            print(
                f"Average rating not available for the driver with id {driver_id}. Calculating average rating from existing ratings for the driver."
            )
            # If avg_rating is not available for some reason, calculate it on the fly based on the existing real(not flagged or spam) ratings for the driver in the database and return it without updating it in the database because we do not want to update avg_rating in the database if it is None for some reason because it might be an indication of some issue with the driver rating records in the database and we do not want to override any existing avg_rating value in the database without investigating the issue further. So we will just calculate and return the average rating on the fly without updating it in the database if avg_rating is None for some reason.
            average_rating = await calculate_average_rating_for_driver(
                driver_id=driver_id,
                db=db,
                exclude_flagged_ratings=True,
                silently_fail=True,
            )
            if average_rating is None:
                raise CabboException(
                    "Average rating not available for the driver and failed to calculate it from existing ratings. No ratings found for the driver.",
                    status_code=404,
                )
        return average_rating
    except Exception as e:
        raise CabboException(
            f"Failed to get average rating for the driver with id {driver_id}: {str(e)}",
            status_code=500,
        )


async def update_average_rating_for_driver(
    driver_id: str,
    db: AsyncSession,
    exclude_flagged_ratings: bool = False,
    silently_fail: bool = False,
) -> Optional[float]:
    """
    Calculate the average rating for a driver based on all the trip ratings provided by customers for their trips and update the average rating for the driver in the database.

    Args:
        driver_id (str): Unique identifier for the driver
        db (AsyncSession): Database session
        exclude_flagged_ratings (bool): A flag to indicate whether to exclude ratings that are flagged as inappropriate or fake from the average rating calculation for the driver to ensure that the average rating reflects genuine customer feedback and experience with the driver. Default is False.
        silently_fail (bool): A flag to indicate whether to silently fail if the driver is not found. Default is False.
    Returns:
        Optional[float]: The average rating for the driver rounded to 2 decimal places after updating it in the database. Returns None if there are no ratings for the driver.
    """
    average_rating = await calculate_average_rating_for_driver(
        driver_id=driver_id,
        db=db,
        exclude_flagged_ratings=exclude_flagged_ratings,
        silently_fail=silently_fail,
    )
    
    try:
            driver = await a_get_driver_by_id(driver_id=driver_id, db=db)
            if not driver:
                if silently_fail:
                    print(
                        f"Driver with id {driver_id} not found. Cannot update average rating for the driver."
                    )
                    return None
                raise CabboException(
                    "Driver not found for the given driver_id", status_code=404
                )
            driver.avg_rating = average_rating
            await db.commit()
            print(
                f"Average rating for driver with id {driver_id} updated to {average_rating}"
            )
            return average_rating
    except Exception as e:
            await db.rollback()
            if silently_fail:
                print(
                    f"Failed to update average rating for the driver with id {driver_id}: {str(e)}"
                )
                return None
            raise CabboException(
                f"Failed to update average rating for the driver: {str(e)}",
                status_code=500,
            )
    

async def fetch_all_trips_for_driver(driver_id: str, db: AsyncSession, status:Optional[TripStatusEnum] = None) -> list[TripSummarySchema]:
    try:
        def _evaluate_driver(driver):
            try:
                driver_schema = DriverReadWithProfilePicture.model_validate(driver) if driver else None
                driver_schema.image_url=f"/images/drivers/{driver_id}.png"
                return driver_schema
            except Exception as e:
                return None
        
        def _evaluate_customer(customer):
            try:
                customer_schema = CustomerReadWithProfilePicture.model_validate(customer) if customer else None
                if customer_schema:
                    customer_schema.image_url=f"/images/customers/{customer_schema.id}.png"
                return customer_schema
            except Exception as e:
                return None
        
        query = select(Trip).where(Trip.driver_id == driver_id)
        if status:
            query = query.where(Trip.status == status)
        result = await db.execute(query)
        trips = result.scalars().all()
        # Map the trips to TripSummarySchema
        if not trips or len(trips) == 0:
            raise CabboException(
                f"No trips found for the driver with id {driver_id} and status {status}",
                status_code=404,
            )
        
        for trip in trips:
            await attach_relationships_to_trip(
                trip, db, expose_customer_details=True
            )
        

        trip_summaries = [
            TripSummarySchema(
                trip_id=trip.id,
                booking_id=trip.booking_id,
                driver=_evaluate_driver(trip.driver),  # Assuming trip.driver is already a DriverReadWithProfilePicture
                customer=_evaluate_customer(trip.customer),  # Assuming trip.customer is already a CustomerReadWithProfilePicture
                trip_type=trip.trip_type_master.trip_type if trip.trip_type_master else None,
                status=trip.status,
                start_datetime=trip.start_datetime,
                end_datetime=trip.end_datetime,
                final_price=trip.final_price,
                price_shown_to_driver=trip.final_display_price,
                num_passengers=trip.num_passengers,
                num_luggages=trip.num_luggages,
                origin=trip.origin,
                destination=trip.destination,
                is_round_trip=trip.is_round_trip,
                is_interstate=trip.is_interstate,
            )
            for trip in trips
        ]
        
        return trip_summaries
 
    except Exception as e:
        raise e
    
 