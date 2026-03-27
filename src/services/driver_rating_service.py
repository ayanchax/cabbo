from typing import List, Optional

from sqlalchemy import select, update
from core.exceptions import CabboException
from core.security import RoleEnum
from models.common import AppBackgroundTask, FlagsEnum
from models.customer.customer_schema import CustomerReadWithProfilePicture
from models.driver.driver_orm import Driver, DriverRating
from models.driver.driver_schema import (
    DriverRatingCreateSchema,
    DriverRatingResponseSchema,
    DriverRatingSchema,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func
from models.trip.trip_enums import TripStatusEnum
from services.customer_service import async_get_customer_by_id
from services.driver_service import a_get_driver_by_id
from services.trips.trip_service import async_get_trip_by_booking_id


async def save_driver_rating_for_trip_by_customer(
    booking_id: str,
    customer_id: str,
    payload: DriverRatingCreateSchema,
    db: AsyncSession,
    validate_time_window=False,
) -> tuple[dict[str, str], Optional[AppBackgroundTask]]:
    """
    Save driver rating and feedback for a trip by a customer. 1 trip -> 1 driver -> 1 rating by customer. If a rating already exists for the trip by the customer for the driver, update the existing rating and feedback with the new values provided in the payload.

    Args:
        booking_id (str): Unique identifier for the trip booking
        customer_id (str): UUID of the customer providing the rating
        payload (DriverRatingCreateSchema): Rating, feedback and overall experience for the driver for the trip provided by the customer
        db (AsyncSession): Database session

    Returns:
        tuple[dict[str, str], Optional[AppBackgroundTask]]: A tuple containing a dictionary with the action performed ("create" or "update") and a message indicating the result of the operation, and an optional background task if any.
    """
    # Note: One can rate inactive driver because when they took the trip the driver was active and they can provide rating for the driver based on their experience during the trip even if the driver becomes inactive later.

    # We only check if the driver was assigned for the trip or not, we do not check if the driver is currently active or not because we want to allow customers to provide ratings for drivers based on their actual experience during the trip regardless of the current status of the driver.

    # Similarly, one can rate a driver for an inactive trip as well because when they took the trip it was active and they can provide rating for the driver based on their experience during the trip even if the trip becomes inactive later. We only check if the trip was completed or not, we do not check if the trip is currently active or not because we want to allow customers to provide ratings for drivers based on their actual experience during the trip regardless of the current status of the trip.

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
    response_dict = {"action": None, "message": None}
    if existing_rating_record:
        await update_driver_rating_for_trip_by_customer(
            rating_record=existing_rating_record, payload=payload, db=db
        )
        response_dict["action"] = "update"
        response_dict["message"] = (
            "Your driver review for the trip has been updated successfully."
        )
    else:
        await create_new_driver_rating_for_trip_by_customer(
            trip_id=trip.id,
            driver_id=trip.driver_id,
            customer_id=customer_id,
            payload=payload,
            db=db,
        )
        response_dict["action"] = "create"
        response_dict["message"] = (
            "Your driver review for the trip has been posted successfully."
        )

    background_task = AppBackgroundTask(
        fn=update_average_rating_for_driver,
        kwargs={
            "driver_id": trip.driver_id,
            "db": db,
            "exclude_flagged_ratings": True,
            "silently_fail": True,  # We want to ensure that even if refunding advance payment fails for some reason, it should not affect the main flow of trip cancellation and marking driver available. So we will silently fail any errors in the background task and log them for future reference.
        },
    )

    return response_dict, background_task


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


async def update_average_rating_for_driver(
    driver_id: str,
    db: AsyncSession,
    exclude_flagged_ratings: bool = False,
    silently_fail: bool = False,
) -> Optional[float]:
    """
    Calculate the average rating for a driver based on all the ratings provided by customers for the driver for their trips and update the average rating for the driver in the database.

    Args:
        driver_id (str): Unique identifier for the driver
        db (AsyncSession): Database session
        exclude_flagged_ratings (bool): A flag to indicate whether to exclude ratings that are flagged as inappropriate or fake from the average rating calculation for the driver to ensure that the average rating reflects genuine customer feedback and experience with the driver. Default is False.
        silently_fail (bool): A flag to indicate whether to silently fail if the driver is not found. Default is False.
    Returns:
        Optional[float]: The average rating for the driver rounded to 2 decimal places after updating it in the database. Returns None if there are no ratings for the driver.
    """
    average_rating = await _calculate_average_rating_for_driver(
        driver_id=driver_id,
        db=db,
        exclude_flagged_ratings=exclude_flagged_ratings,
        silently_fail=silently_fail,
    )
    if average_rating is not None:
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
    if silently_fail:
        print(
            f"No ratings found for the driver with id {driver_id}. Average rating not updated."
        )
        return None
    raise CabboException(
        "Failed to calculate average rating for the driver. Average rating not updated.",
        status_code=500,
    )


async def _calculate_average_rating_for_driver(
    driver_id: str,
    db: AsyncSession,
    exclude_flagged_ratings: bool = False,
    silently_fail: bool = False,
) -> Optional[float]:
    """
    Calculate the average rating for a driver based on all the ratings provided by customers for the driver for their trips.

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
        query = select(func.avg(DriverRating.rating)).where(
            DriverRating.driver_id == driver_id
        )
        if exclude_flagged_ratings:
            # Exclude ratings that are flagged as inappropriate or fake from the average rating calculation for the driver to ensure that the average rating reflects genuine customer feedback and experience with the driver.
            query = query.where(DriverRating.is_flagged == False)

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


async def list_reviews_by_driver_id(
    driver_id: str,
    flag: FlagsEnum,
    db: AsyncSession,
) -> List[DriverRatingResponseSchema]:

    try:

        driver = await a_get_driver_by_id(driver_id=driver_id, db=db)
        if not driver:
            raise CabboException(
                "Driver not found for the given driver_id", status_code=404
            )
        response: List[DriverRatingResponseSchema] = []
        query = select(DriverRating).where(DriverRating.driver_id == driver_id)
        if flag == FlagsEnum.flagged:
            query = query.where(DriverRating.is_flagged == True)
        elif flag == FlagsEnum.unflagged:
            query = query.where(DriverRating.is_flagged == False)
        # For all other values of flag including FlagsEnum.none, we do not apply any filter for flagged status and return all reviews for the driver regardless of their flagged status.
        result = await db.execute(query)
        ratings = result.scalars().all()
        ratings_schema = [
            DriverRatingSchema.model_validate(rating) for rating in ratings
        ]

        for rating in ratings_schema:
            if not rating.customer_id:
                continue
            customer = await async_get_customer_by_id(
                customer_id=rating.customer_id, db=db
            )
            if not customer:
                continue
            customer_schema = CustomerReadWithProfilePicture.model_validate(customer)
            customer_schema.image_url = f"/images/customers/{customer.id}.png"
            rating_response = DriverRatingResponseSchema(
                id=rating.id,
                rating=rating.rating,
                feedback=rating.feedback,
                overall_experience=rating.overall_experience,
                created_at=rating.created_at,
                given_by=customer_schema,
            )
            response.append(rating_response)
        return response

    except Exception as e:
        raise CabboException(
            f"Failed to list driver ratings for the driver with id {driver_id}: {str(e)}",
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
            print(f"Average rating not available for the driver with id {driver_id}. Calculating average rating from existing ratings for the driver.")
            # If avg_rating is not available for some reason, calculate it on the fly based on the existing real(not flagged or spam) ratings for the driver in the database and return it without updating it in the database because we do not want to update avg_rating in the database if it is None for some reason because it might be an indication of some issue with the driver rating records in the database and we do not want to override any existing avg_rating value in the database without investigating the issue further. So we will just calculate and return the average rating on the fly without updating it in the database if avg_rating is None for some reason.
            average_rating = await _calculate_average_rating_for_driver(
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
    
async def fetch_customer_driver_trip_review(
    booking_id  : str,
    customer_id: str,
    db: AsyncSession,
) -> DriverRatingResponseSchema:
    """
    Get the review given by the current customer to a driver for a specific trip.

    Args:
        booking_id (str): Unique identifier for the trip booking
        customer_id (str): UUID of the customer who provided the rating
        db (AsyncSession): Database session
    Returns:
        DriverRatingResponseSchema: The driver rating details including booking_id, driver_id, customer_id, rating, feedback and overall experience for the review given by the current customer to the driver for the specific trip.
    """
    try:
        customer = await async_get_customer_by_id(
            customer_id=customer_id, db=db
        )
        if not customer:
            raise CabboException(
                "Customer not found for the given customer_id", status_code=404
            )
        trip = await async_get_trip_by_booking_id(booking_id=booking_id, db=db)
        if not trip:
            raise CabboException(
                "Trip not found for the given booking_id", status_code=404
            )
        driver_id = trip.driver_id
        if not driver_id:
            raise CabboException(
                "Driver not assigned for the trip. Cannot fetch driver rating for the trip.",
                status_code=400,
            )
        trip_id = trip.id
        
        if not trip_id:
            raise CabboException(
                "Trip ID not available for the trip. Cannot fetch driver rating for the trip.",
                status_code=400,
            )
        if trip.creator_type != RoleEnum.customer:
            raise CabboException(
                "Only customers can have reviews for the driver for a trip",
                status_code=403,
            )
        
        if trip.creator_id != customer_id:
            raise CabboException(
                "Customer is not the creator of the trip and cannot have a review for the driver for the trip",
                status_code=403,
            )
        
        if trip.status != TripStatusEnum.completed:
            raise CabboException(
                "Driver can be rated only for completed trips. Cannot fetch driver rating for the trip.",
                status_code=400,
            )

        
        rating_record = await db.execute(
            select(DriverRating).where(
                DriverRating.driver_id == driver_id,
                DriverRating.trip_id == trip_id,
                DriverRating.customer_id == customer_id,
            )
        )
        rating_record = rating_record.scalar_one_or_none()
        if not rating_record:
            raise CabboException(
                "Driver rating not found.",
                status_code=404,
            )
        
        customer_schema = CustomerReadWithProfilePicture.model_validate(customer)
        customer_schema.image_url = f"/images/customers/{customer.id}.png"
        rating_response = DriverRatingResponseSchema(
            id=rating_record.id,
            rating=rating_record.rating,
            feedback=rating_record.feedback,
            overall_experience=rating_record.overall_experience,
            created_at=rating_record.created_at,
            given_by=customer_schema,
        )
        return rating_response

    except Exception as e:
        raise CabboException(
            f"Failed to get driver rating for the driver against booking {booking_id}: {str(e)}",
            status_code=500,
        )
