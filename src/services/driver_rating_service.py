from typing import Optional

from sqlalchemy import select
from core.exceptions import CabboException
from core.security import RoleEnum
from models.driver.driver_orm import DriverRating
from models.driver.driver_schema import DriverRatingCreateSchema, DriverRatingSchema
from sqlalchemy.ext.asyncio import AsyncSession

from models.trip.trip_enums import TripStatusEnum
from services.trips.trip_service import async_get_trip_by_booking_id


async def save_driver_rating_for_trip_by_customer(
    booking_id: str,
    customer_id: str,
    payload: DriverRatingCreateSchema,
    db: AsyncSession,
    validate_time_window=False
) -> dict[str, str]:
    """
    Save driver rating and feedback for a trip by a customer. 1 trip -> 1 driver -> 1 rating by customer. If a rating already exists for the trip by the customer for the driver, update the existing rating and feedback with the new values provided in the payload.

    Args:
        booking_id (str): Unique identifier for the trip booking
        customer_id (str): UUID of the customer providing the rating
        payload (DriverRatingCreateSchema): Rating, feedback and overall experience for the driver for the trip provided by the customer
        db (AsyncSession): Database session

    Returns:
        dict[str, str]: A dictionary containing the action performed ("create" or "update") and a message indicating the result of the operation.
    """
    #Note: One can rate inactive driver because when they took the trip the driver was active and they can provide rating for the driver based on their experience during the trip even if the driver becomes inactive later. 
    
    # We only check if the driver was assigned for the trip or not, we do not check if the driver is currently active or not because we want to allow customers to provide ratings for drivers based on their actual experience during the trip regardless of the current status of the driver.

    # Similarly, one can rate inactive trip as well because when they took the trip it was active and they can provide rating for the driver based on their experience during the trip even if the trip becomes inactive later. We only check if the trip was completed or not, we do not check if the trip is currently active or not because we want to allow customers to provide ratings for drivers based on their actual experience during the trip regardless of the current status of the trip.
    
    trip = await async_get_trip_by_booking_id(booking_id=booking_id, db=db)
    if not trip:
        raise CabboException("Trip not found for the given booking_id", status_code=404)

    if trip.creator_type != RoleEnum.customer:
        raise CabboException(
            "Only customers can provide rating for the driver for a trip",
            status_code=403,
        )

    if trip.creator_id != customer_id:
        raise CabboException(
            "Customer is not the creator of the trip and cannot provide rating for the driver",
            status_code=403,
        )

    if trip.status != TripStatusEnum.completed:
        raise CabboException(
            "Driver can be rated only for completed trips", status_code=400
        )
    
    if not trip.driver_id:
        raise CabboException(
            "Driver not assigned for the trip yet. Cannot provide rating for the driver.",
            status_code=400,
        )
    
    if validate_time_window:
        # If start_datetime of the trip is in the past then only allow to provide rating
        # We do not want to have spam of ratings for the driver for trips that are scheduled for the future
        # We only want to have ratings for the driver for trips that have already completed or in the past so that the ratings are genuine and based on actual experience of the trip.

        from datetime import datetime, timedelta, timezone
        if not trip.start_datetime:
            raise CabboException(
                "Trip start datetime not available. Cannot validate time window for providing driver rating.",
                status_code=400,
            )
        current_time = datetime.now(timezone.utc)

        if trip.start_datetime > current_time:
            raise CabboException(
                "Driver can be rated only for trips that have completed. Cannot provide rating for the driver before the trip starts.",
                status_code=400,
            )

    # Check if a rating already exists for the trip by the customer for the driver and update the existing rating and feedback with the new values provided in the payload if it exists, otherwise create a new rating entry for the trip by the customer for the driver with the values provided in the payload and return the saved or updated driver rating details including trip_id, driver_id, customer_id,
    # rating, feedback and overall experience
    existing_rating_record = await db.execute(
        select(DriverRating).where(
            DriverRating.trip_id == trip.id,
            DriverRating.driver_id == trip.driver_id,
            DriverRating.customer_id == customer_id,
        )
    )
    existing_rating_record = existing_rating_record.scalar_one_or_none()
    response_dict ={
        "action":None,
        "message":None
    }
    if existing_rating_record:
        await update_driver_rating_for_trip_by_customer(
            rating_record=existing_rating_record, payload=payload, db=db
        )
        response_dict["action"] = "update"
        response_dict["message"] = "Your driver review for the trip has been updated successfully."
    else:
        await create_new_driver_rating_for_trip_by_customer(
            trip_id=trip.id,
            driver_id=trip.driver_id,
            customer_id=customer_id,
            payload=payload,
            db=db,
        )
        response_dict["action"] = "create"
        response_dict["message"] = "Your driver review for the trip has been posted successfully."
    
    return response_dict

async def create_new_driver_rating_for_trip_by_customer(
    trip_id: str,
    driver_id: str,
    customer_id: str,
    payload: DriverRatingCreateSchema,
    db: AsyncSession,
) -> DriverRatingSchema:
    """
    Create a new driver rating and feedback entry for a trip by a customer.

    Args:
        trip_id (str): Unique identifier for the trip
        driver_id (str): Unique identifier for the driver
        customer_id (str): UUID of the customer providing the rating
        payload (DriverRatingCreateSchema): Rating, feedback and overall experience for the driver for the trip provided by the customer
        db (AsyncSession): Database session
    Returns:
        DriverRatingSchema: The saved driver rating details including trip_id, driver_id, customer_id
        rating, feedback and overall experience
    """
    try:
        new_rating = DriverRating(
            trip_id=trip_id,
            driver_id=driver_id,
            customer_id=customer_id,
            rating=payload.rating,
            feedback=payload.feedback or None,
            overall_experience=(
                payload.overall_experience.model_dump()
                if payload.overall_experience is not None
                else None
            ),
        )
        db.add(new_rating)
        await db.commit()
        await db.refresh(new_rating)
        return DriverRatingSchema.model_validate(new_rating)
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to save driver rating for the trip: {str(e)}", status_code=500
        )


async def update_driver_rating_for_trip_by_customer(
    rating_record: DriverRating, payload: DriverRatingCreateSchema, db: AsyncSession
) -> DriverRatingSchema:
    """
    Update driver rating and feedback for a trip by a customer with the new values provided in the payload.

    Args:
        rating_record (DriverRating):Driver rating record entry for the trip by the customer for the driver
        payload (DriverRatingCreateSchema): New rating, feedback and overall experience for the driver for the trip provided by the customer
        db (AsyncSession): Database session

    Returns:
        DriverRatingSchema: The updated driver rating details including trip_id, driver_id, customer_id, rating, feedback and overall experience
    """
    try:
        rating_record.rating = payload.rating or rating_record.rating
        rating_record.feedback = payload.feedback or rating_record.feedback
        rating_record.overall_experience = (
            payload.overall_experience.model_dump()
            if payload.overall_experience is not None
            else rating_record.overall_experience
        )
        db.add(rating_record)
        await db.commit()
        await db.refresh(rating_record)
        return DriverRatingSchema.model_validate(rating_record)
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to update driver rating for the trip: {str(e)}", status_code=500
        )


async def calculate_average_rating_for_driver(
    driver_id: str, db: AsyncSession
) -> Optional[float]:
    """
    Calculate the average rating for a driver based on all the ratings provided by customers for the driver for their trips.

    Args:
        driver_id (str): Unique identifier for the driver
        db (AsyncSession): Database session
    Returns:
        Optional[float]: The average rating for the driver rounded to 2 decimal places. Returns
        None if there are no ratings for the driver.
    """
    try:
        ratings = await db.execute(
            select(DriverRating.rating).where(DriverRating.driver_id == driver_id)
        )
        ratings = ratings.scalars().all()
        if not ratings:
            return None
        average_rating = round(sum(ratings) / len(ratings), 2)
        return average_rating
    except Exception as e:
        raise CabboException(
            f"Failed to calculate average rating for the driver: {str(e)}", status_code=500
        )