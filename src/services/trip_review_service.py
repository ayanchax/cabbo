from typing import List, Optional, Union

from sqlalchemy import select
from core.exceptions import CabboException
from core.security import RoleEnum
from models.common import AppBackgroundTask, FlagsEnum
from models.customer.customer_schema import CustomerRead
from models.driver.driver_orm import TripRating
from sqlalchemy.ext.asyncio import AsyncSession
from models.trip.trip_enums import TripStatusEnum
from models.trip.trip_schema import (
    TripRatingCreateSchema,
    TripRatingResponseSchema,
    TripRatingSchema,
)
from services.customer_service import async_get_customer_by_id
from services.driver_service import a_get_driver_by_id, update_average_rating_for_driver
from services.trips.trip_service import async_get_trip_by_booking_id


async def save_trip_review(
    booking_id: str,
    customer_id: str,
    payload: TripRatingCreateSchema,
    db: AsyncSession,
    validate_time_window=False,
) -> tuple[dict[str, str], Optional[AppBackgroundTask]]:
    """
    Save or update the trip rating and feedback provided by a customer for a driver for a trip and update the average rating for the driver based on all the ratings provided by customers for their trips.
    The review contributes to two aspects:
        The overall trip experience.
        The driver's average rating.

    Args:
        booking_id (str): Unique identifier for the trip booking
        customer_id (str): UUID of the customer providing the rating
        payload (TripRatingCreateSchema): Rating, feedback and overall experience for the driver for the trip provided by the customer
        db (AsyncSession): Database session

    Returns:
        tuple[dict[str, str], Optional[AppBackgroundTask]]: A tuple containing a dictionary with the action performed ("create" or "update") and a message indicating the result of the operation, and an optional background task if any.
    """
    # Note: One can rate a trip for which driver is currently inactive because when they took the trip the driver was active and they can provide rating for the driver based on their experience during the trip even if the driver becomes inactive later.

    # We only check if the driver was assigned for the trip or not, we do not check if the driver is currently active or not because we want to allow customers to provide ratings for drivers based on their actual experience during the trip regardless of the current status of the driver.

    # Similarly, one can rate an inactive trip as well because when they took the trip it was active and they can provide rating for the driver based on their experience during the trip even if the trip becomes inactive later. We only check if the trip was completed or not, we do not check if the trip is currently active or not because we want to allow customers to provide ratings for drivers based on their actual experience during the trip regardless of the current status of the trip.

    trip = await async_get_trip_by_booking_id(booking_id=booking_id, db=db)

    if not trip:
        raise CabboException("Trip not found for the given booking_id", status_code=404)

    if trip.creator_type != RoleEnum.customer:
        raise CabboException(
            "Only customers can provide rating for trip",
            status_code=403,
        )

    if trip.creator_id != customer_id:
        raise CabboException(
            "Customer is not the creator of the trip and cannot provide rating for the trip",
            status_code=403,
        )

    if trip.status != TripStatusEnum.completed:
        raise CabboException(
            "Trip can be rated only if it is completed", status_code=400
        )

    if not trip.driver_id:
        raise CabboException(
            "Driver not assigned for the trip yet. Cannot provide rating for the trip.",
            status_code=400,
        )

    if validate_time_window:
        # If start_datetime of the trip is in the past then only allow to provide rating
        # We do not want to have spam of ratings for the driver for trips that are scheduled for the future
        # We only want to have ratings for the driver for trips that have already completed or in the past so that the ratings are genuine and based on actual experience of the trip.

        from datetime import datetime, timedelta, timezone

        if not trip.start_datetime:
            raise CabboException(
                "Trip start datetime not available. Cannot validate time window for providing trip rating.",
                status_code=400,
            )
        current_time = datetime.now(timezone.utc)

        if trip.start_datetime > current_time:
            raise CabboException(
                "Trip can be rated only if it has started. Cannot provide rating for the trip before it starts.",
                status_code=400,
            )

    # Check if a rating already exists for the trip by the customer for the driver and update the existing rating and feedback with the new values provided in the payload if it exists, otherwise create a new rating entry for the trip by the customer for the driver with the values provided in the payload and return the saved or updated driver rating details including trip_id, driver_id, customer_id,
    # rating, feedback and overall experience
    existing_rating_record = await db.execute(
        select(TripRating).where(
            TripRating.trip_id == trip.id,
            TripRating.driver_id == trip.driver_id,
            TripRating.customer_id == customer_id,
        )
    )
    existing_rating_record = existing_rating_record.scalar_one_or_none()
    response_dict = {"action": None, "message": None}
    if existing_rating_record:
        await update_trip_review(
            rating_record=existing_rating_record, payload=payload, db=db
        )
        response_dict["action"] = "update"
        response_dict["message"] = "Your trip review has been updated successfully."
    else:
        await create_trip_review(
            trip_id=trip.id,
            driver_id=trip.driver_id,
            customer_id=customer_id,
            payload=payload,
            db=db,
        )
        response_dict["action"] = "create"
        response_dict["message"] = "Your trip review has been posted successfully."

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


async def create_trip_review(
    trip_id: str,
    driver_id: str,
    customer_id: str,
    payload: TripRatingCreateSchema,
    db: AsyncSession,
) -> TripRatingSchema:
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
        new_rating = TripRating(
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
        return TripRatingSchema.model_validate(new_rating)
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to save driver rating for the trip: {str(e)}", status_code=500
        )


async def update_trip_review(
    rating_record: TripRating, payload: TripRatingCreateSchema, db: AsyncSession
) -> TripRatingSchema:
    """
    Update trip rating and feedback by a customer with the new values provided in the payload.

    Args:
        rating_record (TripRating): Trip rating record entry for the trip by the customer for the driver
        payload (TripRatingCreateSchema): New rating, feedback and overall experience for the driver for the trip provided by the customer
        db (AsyncSession): Database session

    Returns:
        TripRatingSchema: The updated trip rating details including trip_id, driver_id, customer_id, rating, feedback and overall experience
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
        return TripRatingSchema.model_validate(rating_record)
    except Exception as e:
        await db.rollback()
        raise CabboException(
            f"Failed to update driver rating for the trip: {str(e)}", status_code=500
        )


async def fetch_trip_reviews_by_driver_id(
    driver_id: str,
    flag: FlagsEnum,
    db: AsyncSession,
) -> List[TripRatingResponseSchema]:
    """
    List trip reviews for a given driver provided by various customers.

    Args:
    driver_id (str): Unique identifier for the driver
    flag (FlagsEnum): Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews, and 'none' to retrieve all reviews regardless of their flagged status.
    db (AsyncSession): Database session

    Returns:
    List[TripRatingResponseSchema]: A list of driver rating details including trip_id, driver
    id, customer_id, rating, feedback and overall experience for the reviews of the driver for a given trip provided by various customers.

    """
    try:
        response: List[TripRatingResponseSchema] = []
        query = select(TripRating).where(TripRating.driver_id == driver_id)
        if flag == FlagsEnum.flagged:
            query = query.where(TripRating.is_flagged == True)
        elif flag == FlagsEnum.unflagged:
            query = query.where(TripRating.is_flagged == False)
        # For all other values of flag including FlagsEnum.none, we do not apply any filter for flagged status and return all reviews for the driver regardless of their flagged status.
        result = await db.execute(query)
        ratings = result.scalars().all()
        if not ratings or len(ratings) == 0:
            raise CabboException(
                "No trip reviews found for the given driver_id.", status_code=404
            )
        ratings_schema = [TripRatingSchema.model_validate(rating) for rating in ratings]

        for rating in ratings_schema:
            if not rating.customer_id:
                continue  # to next rating if customer_id is not present for the rating, ideally this should not happen because if a rating exists by a customer then the customer_id should also be present in the database, but we add this check just to be safe and avoid any potential errors in case of any data inconsistencies in the database.
            customer = await async_get_customer_by_id(
                customer_id=rating.customer_id, db=db
            )
            if not customer:
                continue  # to next rating if customer details not found for the rating, ideally this should not happen because if a rating exists by a customer then the customer details should also be present in the database, because we have cascade delete set on this column, the row would not even exist had the customer_id been deleted, but we add this check just to be safe and avoid any potential errors in case of any data inconsistencies in the database.
            customer_schema = CustomerRead.model_validate(customer)
            rating_response = TripRatingResponseSchema(
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
        raise e


async def fetch_trip_reviews_by_customer_id(
    customer_id: str, flag: FlagsEnum, db: AsyncSession
) -> List[TripRatingResponseSchema]:
    """
    List trip reviews given by a specific customer for various trips.

    Args:
        customer_id (str): UUID of the customer
        flag (FlagsEnum): Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews.
        db (AsyncSession): Database session
    Returns:
        List[TripRatingResponseSchema]: A list of trip reviews given by the specified customer.
    """

    try:
        customer = await async_get_customer_by_id(customer_id=customer_id, db=db)
        if not customer:
            raise CabboException(
                "Customer not found for the given customer_id", status_code=404
            )

        response: List[TripRatingResponseSchema] = []
        query = select(TripRating).where(TripRating.customer_id == customer_id)
        if flag == FlagsEnum.flagged:
            # Pick up flagged reviews only for the customer
            query = query.where(TripRating.is_flagged == True)
        elif flag == FlagsEnum.unflagged:
            # Pick up unflagged reviews only for the customer
            query = query.where(TripRating.is_flagged == False)
        # For all other values of flag including FlagsEnum.none, we do not apply any filter for flagged status and return all reviews by the customer regardless of their flagged status.
        result = await db.execute(query)
        ratings = result.scalars().all()
        if not ratings or len(ratings) == 0:
            raise CabboException(
                "No trip reviews found for the given customer_id.", status_code=404
            )
        ratings_schema = [TripRatingSchema.model_validate(rating) for rating in ratings]
        customer_schema = CustomerRead.model_validate(customer)
        for rating in ratings_schema:
            driver = await a_get_driver_by_id(driver_id=rating.driver_id, db=db)
            if not driver:
                continue  # to next rating if driver details not found for the rating, ideally this should not happen because if a rating exists for a driver then the driver details should also be present in the database, because we have cascade delete set on this column, the row would not even exist had the driver_id been deleted, but we add this check just to be safe and avoid any potential errors in case of any data inconsistencies in the database.

            rating_response = TripRatingResponseSchema(
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
        raise e


async def fetch_trip_review_by_trip_id(
    trip_id: str, db: AsyncSession
) -> Optional[TripRatingResponseSchema]:
    """Fetch the trip review for a specific trip.
    Args:
        trip_id (str): Unique identifier for the trip
        db (AsyncSession): Database session
    Returns:
        Optional[TripRatingResponseSchema]: The driver rating details including trip_id, driver_id, customer_id, rating, feedback and overall experience for the review of the driver for a given trip provided by a customer if it exists, otherwise None.
    """
    try:
        result = await db.execute(
            select(TripRating).where(TripRating.trip_id == trip_id)
        )
        rating = result.scalar_one_or_none()
        if not rating:
            raise CabboException(
                "Trip review not found for the given trip_id", status_code=404
            )
        rating_schema = TripRatingSchema.model_validate(rating)
        if not rating_schema.customer_id:
            raise CabboException(
                "Customer ID not found for the trip review. Cannot fetch customer details for the review.",
                status_code=404,
            )
        customer = await async_get_customer_by_id(
            customer_id=rating_schema.customer_id, db=db
        )
        if not customer:
            raise CabboException(
                "Customer not found for the trip review. Cannot fetch customer details for the review.",
                status_code=404,
            )
        customer_schema = CustomerRead.model_validate(customer)
        rating_response = TripRatingResponseSchema(
            id=rating_schema.id,
            rating=rating_schema.rating,
            feedback=rating_schema.feedback,
            overall_experience=rating_schema.overall_experience,
            created_at=rating_schema.created_at,
            given_by=customer_schema,
        )
        return rating_response
    except Exception as e:
        raise e


async def fetch_trip_review_by_review_id(
    review_id: str, db: AsyncSession
) -> Optional[TripRatingResponseSchema]:
    """Fetch the trip review for a specific review id.
    Args:
        review_id (str): Unique identifier for the trip review
        db (AsyncSession): Database session
    Returns:
        Optional[TripRatingResponseSchema]: The driver rating details including trip_id, driver_id, customer_id, rating, feedback and overall experience for the review of the driver for a given trip provided by a customer if it exists, otherwise None.
    """
    try:
        result = await db.execute(select(TripRating).where(TripRating.id == review_id))
        rating = result.scalar_one_or_none()
        if not rating:
            raise CabboException(
                "Trip review not found for the given review_id", status_code=404
            )
        rating_schema = TripRatingSchema.model_validate(rating)
        if not rating_schema.customer_id:
            raise CabboException(
                "Customer ID not found for the trip review. Cannot fetch customer details for the review.",
                status_code=404,
            )
        customer = await async_get_customer_by_id(
            customer_id=rating_schema.customer_id, db=db
        )
        if not customer:
            raise CabboException(
                "Customer not found for the trip review. Cannot fetch customer details for the review.",
                status_code=404,
            )
        customer_schema = CustomerRead.model_validate(customer)
        rating_response = TripRatingResponseSchema(
            id=rating_schema.id,
            rating=rating_schema.rating,
            feedback=rating_schema.feedback,
            overall_experience=rating_schema.overall_experience,
            created_at=rating_schema.created_at,
            given_by=customer_schema,
        )
        return rating_response
    
    except Exception as e:
        raise e


async def fetch_trip_review_by_booking_id_customer_id(
    booking_id: str,
    customer_id: str,
    db: AsyncSession,
) -> TripRatingResponseSchema:
    """
    Get the review given by a customer for a specific trip.

    Args:
        booking_id (str): Unique identifier for the trip booking
        customer_id (str): UUID of the customer who provided the rating
        db (AsyncSession): Database session
    Returns:
        TripRatingResponseSchema: The driver rating details including booking_id, driver_id, customer_id, rating, feedback and overall experience for the review given by the current customer for the specific trip.
    """
    try:
        customer = await async_get_customer_by_id(customer_id=customer_id, db=db)
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
                "Customer is not the creator of the trip and cannot view the review for the driver for the trip",
                status_code=403,
            )

        if trip.status != TripStatusEnum.completed:
            raise CabboException(
                "Driver can be rated only for completed trips. Cannot fetch driver rating for the trip.",
                status_code=400,
            )

        rating_record = await db.execute(
            select(TripRating).where(
                TripRating.driver_id == driver_id,
                TripRating.trip_id == trip_id,
                TripRating.customer_id == customer_id,
            )
        )
        rating_record = rating_record.scalar_one_or_none()
        if not rating_record:
            raise CabboException(
                "Driver rating not found.",
                status_code=404,
            )

        customer_schema = CustomerRead.model_validate(customer)
        rating_response = TripRatingResponseSchema(
            id=rating_record.id,
            rating=rating_record.rating,
            feedback=rating_record.feedback,
            overall_experience=rating_record.overall_experience,
            created_at=rating_record.created_at,
            given_by=customer_schema,
        )
        return rating_response

    except Exception as e:
        raise e


async def fetch_all_trip_reviews(
    flag: FlagsEnum, db: AsyncSession
) -> List[TripRatingResponseSchema]:
    """
    List all trip reviews by various customers to various drivers.

    Args:
        flag (FlagsEnum): Filter reviews based on their flagged status. Use 'flagged' to retrieve only flagged reviews, 'unflagged' to retrieve only non-flagged reviews.
        db (AsyncSession): Database session

    Returns:
        List[TripRatingResponseSchema]: A list of trip reviews by various customers to various drivers.
    """
    try:
        response: List[TripRatingResponseSchema] = []
        query = select(TripRating)
        if flag == FlagsEnum.flagged:
            # Pick up flagged reviews only
            query = query.where(TripRating.is_flagged == True)
        elif flag == FlagsEnum.unflagged:
            # Pick up unflagged reviews only
            query = query.where(TripRating.is_flagged == False)
        # For all other values of flag including FlagsEnum.none, we do not apply any filter for flagged status and return all reviews regardless of their flagged status.
        result = await db.execute(query)
        ratings = result.scalars().all()
        if not ratings or len(ratings) == 0:
            raise CabboException(
                "No trip reviews found.", status_code=404
            )
        ratings_schema = [TripRatingSchema.model_validate(rating) for rating in ratings]
        for rating in ratings_schema:
            if not rating.customer_id:
                continue  # to next rating if customer_id is not present for the rating, ideally this should not happen because if a rating exists by a customer then the customer_id should also be present in the database, but we add this check just to be safe and avoid any potential errors in case of any data inconsistencies in the database.
            customer = await async_get_customer_by_id(
                customer_id=rating.customer_id, db=db
            )
            if not customer:
                continue  # to next rating if customer details not found for the rating, ideally this should not happen because if a rating exists by a customer then the customer details should also be present in the database, because we have cascade delete set on this column, the row would not even exist had the customer_id been deleted, but we add this check just to be safe and avoid any potential errors in case of any data inconsistencies in the database.
            customer_schema = CustomerRead.model_validate(customer)
            rating_response = TripRatingResponseSchema(
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
        raise e


async def update_trip_review_flag_status(
    review_id: str, is_flagged: bool, db: AsyncSession
) -> tuple[bool, Optional[Union[str, AppBackgroundTask]]]:
    """
    Update the flagged status of a trip review.

    Args:
        review_id (str): Unique identifier for the trip review
        is_flagged (bool): The new flagged status to be set for the trip review
        db (AsyncSession): Database session

    Returns:
        tuple[bool, Optional[Union[str, AppBackgroundTask]]]: A tuple containing a boolean indicating if the update was successful and an optional message or background task.
    """
    try:
        rating_record = await db.execute(
            select(TripRating).where(TripRating.id == review_id)
        )
        rating_record = rating_record.scalar_one_or_none()
        if not rating_record:
            raise CabboException(
                "Trip review not found for the given review_id", status_code=404
            )
        existing_flagged_status = rating_record.is_flagged
        if existing_flagged_status == is_flagged:
            # If the existing flagged status is same as the new flagged status, then we do not need to update and can return early.
            return (
                False,
                "No update needed as the flagged status is already set to the desired value.",
            )
        rating_record.is_flagged = is_flagged
        db.add(rating_record)
        await db.commit()
        # We will update the average rating for the driver based on all the ratings provided by customers for their trips
        # to ensure that the average rating reflects genuine customer feedback and experience with the driver.
        # If a review is flagged as inappropriate or fake, then we will exclude that review from the average rating calculation
        # for the driver to ensure that the average rating reflects genuine customer feedback and experience with the driver.
        # That is why we need to update avg rating of driver whenever the flagged status of a review is updated because it can impact the average rating of the driver.
        background_task = AppBackgroundTask(
            fn=update_average_rating_for_driver,
            kwargs={
                "driver_id": rating_record.driver_id,
                "db": db,
                "exclude_flagged_ratings": True,
                "silently_fail": True,  # We want to ensure that even if refunding advance payment fails for some reason, it should not affect the main flow of trip cancellation and marking driver available. So we will silently fail any errors in the background task and log them for future reference.
            },
        )
        return True, background_task
    except Exception as e:
        await db.rollback()
        raise e
