from datetime import datetime, timezone, timedelta
from typing import Optional, Union
from core.exceptions import CabboException
from core.trip_helpers import attach_relationships_to_trip
from models.common import AppBackgroundTask
from models.customer.customer_orm import Customer
from models.trip.trip_enums import CancellationSubStatusEnum, TripStatusEnum, TripTypeEnum
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    AdditionalDetailsOnTripStatusChange,
    TripDetailSchema,
)
from models.user.user_orm import User
from services.audit_trail_service import a_log_trip_audit
from services.cancelation_service import (
    get_cancelation_payload,
    get_cancelation_sub_status,
    get_cancellation_by_trip_id,
    register_trip_cancellation,
    remove_cancellation_by_trip_id,
)
from services.dispute_service import register_trip_dispute
from services.driver_service import (
    add_driver_earning_record,
    delete_driver_earning,
    get_trip_earning_for_driver,
    toggle_availability_of_driver,
)
from sqlalchemy.ext.asyncio import AsyncSession

from services.refund_service import refund_advance_payment_to_customer_on_cancellation


async def change_status(
    trip: Trip,
    db: AsyncSession,
    status: TripStatusEnum,
    requestor: Union[User, Customer],
    payload: Optional[AdditionalDetailsOnTripStatusChange],
    validate_time_window: bool = False,  # Added a flag to allow skipping time window validation for certain scenarios like marking past trips as ongoing for record keeping or analysis purposes, but by default we will validate the time window to ensure better accuracy in trip records and also to avoid any misuse or accidental marking of trip as ongoing well before the actual start time which can create confusion and issues in driver allocation and customer experience.
):
    
    trip_type = trip.trip_type_master.trip_type
    if not trip_type:
            raise CabboException(
                "Invalid trip type associated with the trip. Please ensure the trip has a valid trip type before starting the trip.",
                status_code=400,
            )
    if not payload:
            payload = AdditionalDetailsOnTripStatusChange()  # Create a new payload if not provided to pass the evaluated start datetime to the background task of logging audit trail for trip status change and also for better consistency in the flow of marking trip as ongoing and logging audit trail with the same payload.
            
    if status == TripStatusEnum.ongoing:
        if validate_time_window:
            trip_type = TripTypeEnum(trip_type)
            now = datetime.now(timezone.utc)
            #payload.start_datetime can be provided as overriden value by driver_admin when they are marking the trip as ongoing, because sometimes the driver might have started the trip a bit earlier than the scheduled start time due to traffic conditions, customer readiness etc. and in such cases we want to allow driver_admin to provide the actual start datetime when marking the trip as ongoing for better accuracy in trip records and also for better analysis of trip data in the future. But if payload.start_datetime is not provided then we will use the original start datetime of the trip for further processing in the flow of marking trip as ongoing.
            scheduled_start_time = _evaluate_start_time(trip.start_datetime, payload.start_datetime if payload else None)
            buffer_times ={
                TripTypeEnum.airport_drop: 60,  # For airport trips we will allow to mark the trip as ongoing within 60 minutes before the scheduled start time considering the potential traffic conditions and other factors that can affect the timely arrival of driver at airport and also considering the short notice and potential driver inconvenience in case of airport trips.
                TripTypeEnum.airport_pickup: 60,  # For airport trips we will allow to mark the trip as ongoing within 60 minutes before the scheduled start time considering the potential traffic conditions and other factors that can affect the timely arrival of driver at airport and also considering the short notice and potential driver inconvenience in case of airport trips.
                TripTypeEnum.local: 0,  # For local trips we will not allow to mark the trip as ongoing before the scheduled start time to ensure better accuracy in trip records and also to avoid any misuse or accidental marking of trip as ongoing well before the actual start time which can create confusion and issues in driver allocation and customer experience.
                TripTypeEnum.outstation: 0,  # For outstation trips we will not allow to mark the trip as ongoing before the scheduled start time to ensure better accuracy in trip records and also to avoid any misuse or accidental marking of trip as ongoing well before the actual start time which can create confusion and issues in driver allocation and customer experience.
            }
            buffer_time_minutes = buffer_times.get(trip_type, 0)
            
            #Past trip guard
            # Block past trips, only allow trips that are scheduled to start in the future or within the buffer time window for trips to be marked as ongoing, because we do not want to allow marking of past trips as ongoing to avoid any misuse or accidental marking of old trips as ongoing which can create confusion and issues in driver allocation and customer experience. For non-airport trips, we will not allow to mark the trip as ongoing before the scheduled start time to ensure better accuracy in trip records and also to avoid any misuse or accidental marking of trip as ongoing well before the actual start time which can create confusion and issues in driver allocation and customer experience.
            
            if now > scheduled_start_time + timedelta(minutes=buffer_time_minutes):
                raise CabboException(
                    f"Cannot start trip after {(now - scheduled_start_time).total_seconds() // 60} minutes of the start time. Please ensure to mark the trip as ongoing within the allowed time window considering the short notice and potential driver inconvenience.",
                    status_code=400,
                )

            #Do not start too early guard
            #Trip can be marked as ongoing if current time is equal to or after the start time minus buffer time for trips considering the short notice and potential driver inconvenience, but we will not allow to mark the trip as ongoing much before the start time to avoid any misuse or accidental marking of trip as ongoing well before the actual start time which can create confusion and issues in driver allocation and customer experience.
            if now < scheduled_start_time - timedelta(minutes=buffer_time_minutes):
                    raise CabboException(
                        f"Cannot start trip before {(scheduled_start_time - now).total_seconds() // 60} minutes of the start time. Please ensure to mark the trip as ongoing within the allowed time window considering the short notice and potential driver inconvenience.",
                        status_code=400,
                    )
            payload.start_datetime = scheduled_start_time  # Update the start datetime in the payload with the evaluated start datetime which is based on the original start datetime of the trip and any overridden start datetime provided in the payload, so that we can use this start datetime for further processing in the flow of marking trip as ongoing and also to log in the audit trail for trip status change.
        return await _ongoing(
            trip=trip, db=db, status=status, requestor=requestor, payload=payload
        )

    elif status == TripStatusEnum.completed:
        return await _complete(
            trip=trip, db=db, status=status, requestor=requestor, payload=payload
        )

    elif status == TripStatusEnum.cancelled:
        return await _cancelled(
            trip=trip, db=db, status=status, requestor=requestor, payload=payload
        )

    elif status == TripStatusEnum.dispute:
        return await _dispute(
            trip=trip, db=db, status=status, requestor=requestor, payload=payload
        )
    else:
        raise CabboException("Invalid status update requested", status_code=400)

async def _ongoing(
    trip: Trip,
    db: AsyncSession,
    status: TripStatusEnum,
    requestor: Union[User,Customer],
    payload: Optional[AdditionalDetailsOnTripStatusChange],
):

        if not trip.advance_payment or trip.advance_payment <= 0:
            raise CabboException(
                "Cannot start trip without a valid advance payment. Please ensure the customer has made the advance payment and the payment is reflected in the system before starting the trip.",
                status_code=400,
            )

        if not trip.balance_payment or trip.balance_payment <= 0:
            raise CabboException(
                "Cannot start trip without a valid balance payment. Please ensure the customer has made the advance payment and the payment is reflected in the system before starting the trip.",
                status_code=400,
            )

        if trip.driver_id is None:
            # Cannot silently assign a random driver, thus we will raise an exception if there is no driver assigned to the trip when we are trying to mark it as ongoing because a trip cannot start without a driver. The driver assignment should have happened at the time of confirming the trip booking and if for some reason the driver assignment did not happen then it should be fixed before starting the trip.
            raise CabboException(
                "Cannot start trip without an assigned driver", status_code=400
            )

        existing_record = await get_trip_earning_for_driver(
            trip_id=trip.id, driver_id=trip.driver_id, db=db
        )
        if existing_record:
            # Silently delete any bad data
            await delete_driver_earning(
                earning_id=existing_record.id, db=db, hard_delete=True, commit=False
            )

        if (
            trip.driver
            and trip.driver_id == trip.driver.id
            and trip.driver.is_available
        ):
            # Silently handle the scenario where driver is still marked available due to some reason (like app crash, network issue etc.) after they were assigned to the trip but before the trip was marked as ongoing. In this case, we will log a warning and proceed with marking the trip as ongoing and setting the start datetime because we do not want to block the trip from starting just because of an issue in updating driver availability status in the system.
            print(
                f"Warning: Driver {trip.driver_id} is still marked as available even after they were assigned for this trip: {trip.id}. Proceeding with marking trip as ongoing and setting start datetime. Marking driver unavailable again to ensure smooth flow of the trip."
            )
            trip.driver.is_available = False
            await db.flush()  # Flush to save the updated driver availability status before any further operations

        # Update start datetime - The driver_admin can get the actual start datetime from the driver when they start the trip in the driver app, if not provided we will set the start datetime as current datetime in UTC timezone.
        trip.start_datetime =payload.start_datetime if payload and payload.start_datetime else _evaluate_start_time(startdatetime=trip.start_datetime)  # Set the actual start datetime when trip is marked as ongoing
        # Update status
        trip.status = status.value

        # Log audit trail for trip start
        reason = payload.reason if payload and payload.reason else "No reason provided"
        print(f"Logging audit trail for trip start with reason: {reason}")
        await a_log_trip_audit(
            trip_id=trip.id,
            status=status,
            committer_id=requestor.id,
            reason=f"Trip started. {reason}",
            db=db,
            commit=False,  # Defer commit to batch with trip update
        )
        await db.flush()  # Flush to ensure the start_datetime and status update is saved before any further operations
        await db.commit()
        await db.refresh(trip)
        await attach_relationships_to_trip(trip, db, expose_customer_details=True, expose_cancellation_detail=True)
        return TripDetailSchema.model_validate(trip), None
     

async def _complete(
    trip: Trip,
    db: AsyncSession,
    status: TripStatusEnum,
    requestor: Union[User, Customer],
    payload: Optional[AdditionalDetailsOnTripStatusChange],
):
    
        if not trip.advance_payment or trip.advance_payment <= 0:
            raise CabboException(
                "Cannot complete trip without a valid advance payment. Please ensure the customer has made the advance payment and the payment is reflected in the system before completing the trip.",
                status_code=400,
            )

        if not trip.balance_payment or trip.balance_payment <= 0:
            raise CabboException(
                "Cannot complete trip without a valid balance payment. Please ensure the customer has made the balance payment and the payment is reflected in the system before completing the trip.",
                status_code=400,
            )

        if trip.driver_id is None:
            raise CabboException(
                "Cannot complete trip without an assigned driver", status_code=400
            )

        # Update end datetime with the actual end datetime when trip is completed. The driver_admin can get the actual end datetime from the driver, if not provided we will set the end datetime as current datetime in UTC timezone.
        trip.end_datetime = (
            payload.end_datetime
            if payload and payload.end_datetime
            else datetime.now(timezone.utc)
        )  # Set the actual end datetime when trip is completed

        # Update status
        trip.status = status.value

        # Set balance_payment zero, because a completed trip can only be marked as complete once the driver_admin confirms the trip completion from the driver (and gather additional details like actual end datetime, ensures remaining fare was paid to driver etc.)
        # and at that point we can be sure about the final price and there should not be any balance payment pending from customer. In case of any change in price after trip completion, we will not handle that because all remaining payments are paid directly to driver and we will not be handling any post trip completion price adjustments in the system for now.
        # In case of disputes where customer did not pay the driver the remaining amount or any extra charges, then we will mark the trip as dispute and try to resolve it between the two parties.
        # Our driver will not over charge the customer at the end of the trip, customer needs to pay only what is showing as remaining in the app (plus any additional charges of tolls, paid parking, additional mileage etc. subject to proof/reciepts shown by driver to customer.)

        # Update balance payment to 0.0
        trip.balance_payment = 0.0

        # Free up the driver
        await toggle_availability_of_driver(
            driver_id=trip.driver_id, db=db, make_available=True, commit=False
        )

        # Log audit trail for trip completion
        reason = payload.reason if payload and payload.reason else "No reason provided"
        print(f"Logging audit trail for trip completion with reason: {reason}")

        await a_log_trip_audit(
            trip_id=trip.id,
            status=status,
            committer_id=requestor.id,
            reason=f"Trip completed. {reason}",
            db=db,
            commit=False,  # Defer commit to batch with trip update
        )
        await db.flush()  # Flush to ensure the end_datetime, status update, balance payment update and extra payment details are saved before any further operations
        await db.commit()
        await db.refresh(trip)

        # Add a record to DriverEarning for the amount paid to driver - Background Task
        # Delegating the task of adding driver earning record to background task because it is a secondary work and also to ensure that the main flow of trip completion and marking driver available is not affected by any potential issues in adding driver earning record and also to improve the response time for trip completion API.
        await attach_relationships_to_trip(trip, db, expose_customer_details=True, expose_cancellation_detail=True)
        trip_schema = TripDetailSchema.model_validate(
            trip
        )  # Convert the serialized trip dictionary back to TripDetails schema for better type safety and to ensure we are passing the correct data structure to the background task of adding driver earning record.
        background_task = AppBackgroundTask(
            fn=add_driver_earning_record,
            kwargs={
                "trip": trip_schema,
                "additional_info": payload,
                "db": db,
                "requestor": requestor.id,
                "silently_fail": True,  # We want to ensure that even if adding driver earning record fails for some reason, it should not affect the main flow of trip completion and marking driver available. So we will silently fail any errors in the background task and log them for future reference.
            },
        )
        return trip_schema, background_task
     

async def _cancelled(
    trip: Trip,
    db: AsyncSession,
    status: TripStatusEnum,
    requestor: Union[User, Customer],
    payload: Optional[AdditionalDetailsOnTripStatusChange],
):
     
        existing_cancellation_record = await get_cancellation_by_trip_id(
            trip_id=trip.id, db=db
        )
        if existing_cancellation_record:
            # Clean bad data
            await remove_cancellation_by_trip_id(
                trip_id=trip.id, db=db, hard_delete=True
            )

        # A canceled trip may or may not have an assigned driver, so we do not check for driver assignment before allowing cancellation. We allow cancellation of a trip without an assigned driver because sometimes customers may want to cancel a trip before a driver is assigned to avoid any inconvenience and also to allow them to book a new trip with correct details if they made any mistake in the initial booking.
        if not trip.advance_payment or trip.advance_payment <= 0:
            raise CabboException(
                "Cannot cancel trip without a valid advance payment. Please ensure the customer has made the advance payment and the payment is reflected in the system before canceling the trip.",
                status_code=400,
            )

        # Update status.
        trip.status = status.value

        # Set balance payment to 0.0 because once a trip is canceled there should not be any balance payment pending from customer. In case of any cancellation charges, we will not be handling that in the system for now and we will assume that the customer will take care of any cancellation charges directly with the driver and we will not be deducting any cancellation charges from the advance payment in the system for now.
        trip.balance_payment = 0.0

        if trip.driver_id:
            # Free up the driver if already assigned to the trip.
            await toggle_availability_of_driver(
                driver_id=trip.driver_id, db=db, make_available=True, commit=False
            )

        cancelation_sub_status = get_cancelation_sub_status(
            requestor=requestor,
            creator_id=trip.creator_id,
            cancelation_detail=payload.cancelation_detail if payload else None,
        )
        cancelation_payload = get_cancelation_payload(
            cancelation_detail=(
                payload.cancelation_detail
                if payload and payload.cancelation_detail
                else None
            ),
            trip_id=trip.id,
            user_id=requestor.id,
            cancelation_sub_status=cancelation_sub_status,
        )
       
        payload.cancelation_detail = cancelation_payload  # Update the existing payload with the cancelation detail to pass it to the background task of registering trip cancellation details in the system and also to log in the audit trail for trip cancellation.
        cancelation_record = await register_trip_cancellation(
            payload=payload.cancelation_detail, db=db, silently_fail=True, commit=False
        )  # Register trip cancellation details in the system - This will help us to keep track of all cancellations and also to analyze the cancellation reasons and patterns in the future to improve our service and reduce cancellations.

        if not cancelation_record:
            raise CabboException(
                "Failed to register trip cancellation details in the system",
                status_code=500,
            )

        # Log audit trail for trip cancellation
        reason = (
            payload.cancelation_detail.reason
            if payload
            and payload.cancelation_detail
            and payload.cancelation_detail.reason
            else "No cancellation reason provided"
        )
        print(f"Logging audit trail for trip cancellation with reason: {reason}")

        await a_log_trip_audit(
            trip_id=trip.id,
            status=status,
            committer_id=requestor.id,
            reason=f"Trip cancelled. {reason} ",
            db=db,
            commit=False,  # Defer commit to batch with trip update
        )
        await db.flush()  # Flush to ensure the status update and audit log is saved before any further operations
        await db.commit()
        await db.refresh(trip)
        await attach_relationships_to_trip(
            trip, db, expose_customer_details=True, expose_cancellation_detail=True
        )
        trip_schema = TripDetailSchema.model_validate(trip)

        background_task = AppBackgroundTask(
            fn=refund_advance_payment_to_customer_on_cancellation,
            kwargs={
                "trip": trip_schema,
                "db": db,
                "cancelation_sub_status": cancelation_sub_status,
                "silently_fail": True,  # We want to ensure that even if refunding advance payment fails for some reason, it should not affect the main flow of trip cancellation and marking driver available. So we will silently fail any errors in the background task and log them for future reference.
                "requestor": requestor.id,
            },
        )
        return trip_schema, background_task
     

async def _dispute(
    trip: Trip,
    db: AsyncSession,
    status: TripStatusEnum,
    requestor: Union[User, Customer],
    payload: Optional[AdditionalDetailsOnTripStatusChange],
):
    
        if not trip.advance_payment or trip.advance_payment <= 0:
            raise CabboException(
                "Cannot mark trip as dispute without a valid advance payment. Please ensure the customer has made the advance payment and the payment is reflected in the system before marking the trip as dispute.",
                status_code=400,
            )

        # A disputed trip must have an assigned driver, so we check for driver assignment before allowing to mark a trip as dispute. We want to ensure that a trip cannot be marked as dispute without an assigned driver because in case of disputes we need to involve the driver and also need to investigate the trip details and driver behavior during the trip to resolve the dispute, and it would be difficult to do that if there is no assigned driver for the trip.
        if trip.driver_id is None:
            raise CabboException(
                "Cannot mark trip as dispute without an assigned driver",
                status_code=400,
            )

        # Update status
        trip.status = status.value

        # we do not set balance payment to 0.0 in case of dispute because in case of disputes we want to keep the payment details intact in the system for better investigation and resolution of the dispute, and also to ensure that the customer and driver are aware of the payment details during the dispute resolution process. In case of disputes, we will try to resolve the issue between the customer and driver and if needed we can involve our support team to mediate and find a fair solution for both parties, but we will not be making any changes to the payment details in the system until the dispute is resolved because any changes to payment details during an ongoing dispute can create confusion and make it difficult to resolve the dispute in a fair manner.

        # Free up the driver anyway because in case of dispute the driver should not be blocked for new trips and also to ensure that the driver is available for any ongoing trips they might have after this trip which is now marked as dispute.
        await toggle_availability_of_driver(
            driver_id=trip.driver_id, db=db, make_available=True, commit=False
        )

        # Log audit trail for marking trip as dispute
        reason = (
            payload.dispute_detail.reason
            if payload and payload.dispute_detail and payload.dispute_detail.reason
            else "No dispute reason provided"
        )
        print(f"Logging audit trail for trip dispute with reason: {reason}")

        await a_log_trip_audit(
            trip_id=trip.id,
            status=status,
            committer_id=requestor.id,
            reason=f"Trip marked as dispute. {reason}",
            db=db,
            commit=False,  # Defer commit to batch with trip update
        )
        await db.flush()  # Flush to ensure the status update and audit log is saved before any further operations
        await db.commit()
        await db.refresh(trip)
        await attach_relationships_to_trip(trip, db, expose_customer_details=True, expose_cancellation_detail=True)
        trip_schema = TripDetailSchema.model_validate(trip)
        # Create a dispute record in the system for this trip - Background Task
        background_task = AppBackgroundTask(
            fn=register_trip_dispute,
            kwargs={
                "trip": trip_schema,
                "payload": (
                    payload.dispute_detail
                    if payload and payload.dispute_detail
                    else None
                ),
                "db": db,
                "requestor": requestor.id,
                "silently_fail": True,  # We want to ensure that even if creating dispute record fails for some reason, it should not affect the main flow of marking trip as dispute and free up driver. So we will silently fail any errors in the background task and log them for future reference.
            },
        )
        return trip_schema, background_task
     
    
def _evaluate_start_time(startdatetime: datetime, overridden_startdatetime: Optional[datetime]=None):
    if overridden_startdatetime:
        dt = overridden_startdatetime
    else:
        dt = startdatetime if startdatetime else datetime.now(timezone.utc)
    # Normalise to UTC-aware — MySQL returns naive datetimes stored as UTC
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
