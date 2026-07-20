from fastapi import APIRouter, Depends, Path
from core.exceptions import CabboException
from core.security import validate_customer_token
from core.trip_helpers import get_prior_booking_window_hours, get_trip_constraints_by_trip_type
from db.database import yield_mysql_session
from models.customer.customer_orm import Customer
from models.trip.trip_enums import TripStatusEnum, TripTypeEnum
from models.trip.trip_schema import (
    TripBookRequest,
    TripOut,
    TripSearchRequest,
)

from sqlalchemy.orm import Session
from services.configuration_service import get_all_cabs
from services.trips.trip_service import get_trip_messages
from services.trips.booking_service import (
    confirm_trip_booking,
    delete_temp_trip_by_booking_id,
    initiate_trip_booking,
    verify_temp_trip_platform_fee,
)
from services.trips.search_service import search
from utils.utility import remove_none_recursive
from .reviews import router as trip_reviews
from .refunds import router as trip_refunds
from .bookings import router as trip_bookings
from .classifier import router as trip_type_classifier
from .package import router as trip_packages
from .fleet import router as fleet_router
from .support import router as trip_support_router


router = APIRouter()


# Trip booking endpoints for customers to search for trips, initiate trip bookings, confirm trip bookings after payment and cleanup trip data for abandoned trips. These endpoints will validate the JWT token to ensure that only authenticated customers can access these functionalities and manage their trips securely. The search endpoint will allow customers to search for available trips based on their preferences and criteria, while the booking endpoints will handle the initiation and confirmation of trip bookings, as well as cleanup of trip data for abandoned or failed bookings to maintain data integrity and optimize storage. Additionally, there is an endpoint for fetching refund details for a specific booking, which will allow customers to view the status and details of their refunds in case of cancellations or other issues with their trips.


@router.post("/search", tags=["customer-trip-search"])
def search_trip(
    search_in: TripSearchRequest,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    result = search(search_in=search_in, requestor=current_customer.id, db=db)
    return remove_none_recursive(result.model_dump())


@router.post("/initiate-booking", response_model=dict, tags=["customer-trip-booking"])
def init_booking(
    trip_in: TripBookRequest,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    trip_id, order = initiate_trip_booking(
        booking_request=trip_in, customer=current_customer, db=db
    )

    
    response =  {
        "trip_id": trip_id,  # This is the temp trip id created for the booking
        "order_id": order.get("id"),
        "amount": order.get("amount"),
        "amount_in_lowest_unit": order.get("amount_in_lowest_unit"),
        "currency": order.get("currency"),
        "currency_symbol": order.get("currency_symbol"),
        "description": order.get("description"),
        "customer": order.get("notes", {}).get("customer", {}),
        "status": order.get("status"),
        **get_trip_messages(status=TripStatusEnum.created),
        
    }
    #Pop id from customer
    if "customer" in response and isinstance(response["customer"], dict) and "id" in response["customer"]:
        response["customer"].pop("id", None)

    fleet= None
    if trip_in.preferences.retrieve_fleet:
        #If the request includes a flag to retrieve fleet information, fetch the fleet details based on the car type preference specified in the trip booking request and include it in the response. This allows customers to view the available fleet options that match their preferences when initiating a trip booking, enhancing their booking experience and enabling them to make informed decisions about their trip options.
        all_cabs = get_all_cabs(db)
        preferred_cab = next((cab for cab in all_cabs if cab.name.lower() == trip_in.option.car_type.value.lower()), None)
        fleet = preferred_cab.model_dump(exclude_none=True, exclude={"id","created_by","is_active"}) if preferred_cab else None
        response["fleet"] = fleet
    return response



@router.post("/confirm-booking", response_model=dict, tags=["customer-trip-booking"])
def confirm_booking(
    booking: TripOut,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Confirm the trip booking after payment is successful.
    """
    created_trip = confirm_trip_booking(
        booking_request=booking, customer=current_customer, db=db
    )
    return {
        "booking_id": created_trip.booking_id,
        **get_trip_messages(status=TripStatusEnum.confirmed),
    }


@router.delete(
    "/cleanup/{booking_id}", response_model=dict, tags=["customer-trip-booking"]
)
def cleanup_temp_trip_booking(
    booking_id: str,
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    """
    Cleanup trip data for the customer.
    This endpoint is invoked silently from frontend when the customer abandons the trip search or payment page midway or payment fails.
    """
    is_deleted = delete_temp_trip_by_booking_id(
        booking_id=booking_id, requestor=current_customer.id, db=db
    )
    if is_deleted:
        return {"message": "Trip data cleaned up successfully."}
    return {"message": "Failed to clean up trip data."}


@router.get(
    "/prior-booking-window/{trip_type}/{jurisdiction_code}",
    response_model=int,
    tags=["customer-trip-booking"],
)
def get_prior_booking_window(
    trip_type: TripTypeEnum,
    jurisdiction_code: str,
    _: Customer = Depends(validate_customer_token),
):
    """
    Get the prior booking window hours for a given trip type and jurisdiction code (region or state).
    This endpoint will help customers understand how far in advance they need to book their trips based on the trip type and location.
    """
    return get_prior_booking_window_hours(
        trip_type=trip_type, jurisdiction_code=jurisdiction_code
    )



@router.get(
    "/constraints/{trip_type}/{jurisdiction_code}",
    response_model=dict,
    tags=["customer-trip-booking"],
)
def get_trip_constraints(
    trip_type: TripTypeEnum,
    jurisdiction_code: str,
    db: Session = Depends(yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
   
    return get_trip_constraints_by_trip_type(
        trip_type=trip_type, jurisdiction_code=jurisdiction_code, db=db
    )


@router.get("/verify/cost/{id}/{cost}")
def verify_trip_cost(
    id: str = Path(..., description="Temp trip id to verify the cost for"),
    cost: float = Path(
        ...,
        description="Cost to verify against actual/expected trip cost",
        ge=100,
        le=1200,
    ),
    db: Session = Depends(yield_mysql_session),
    current_customer: Customer = Depends(validate_customer_token),
):
    # Reverify the platform fee before opening Razorpay checkout. If a client
    # payload was tampered with, fail before the payment modal is initialized.
    return {
        "verified": verify_temp_trip_platform_fee(
            temp_trip_id=id,
            requestor=current_customer.id,
            cost=cost,
            db=db,
        )
    }

# Trip review endpoints for customers to provide ratings and feedback for their trips and view their reviews. These endpoints will validate the JWT token to ensure that only authenticated customers can access these functionalities and manage their trip reviews securely. The review endpoint will allow customers to submit their ratings and feedback for their completed trips, while the view reviews endpoint will enable customers to view their submitted reviews, enhancing the overall user experience and enabling better service quality through customer feedback.
router.include_router(
    trip_reviews, prefix="/reviews", tags=["customer-trip-review-management"]
)

# Trip refund endpoints for customers to fetch refund details for their bookings. This will allow customers to view the status and details of their refunds in case of cancellations or other issues with their trips. This endpoint will validate the JWT token to ensure that only authenticated customers can access their refund details securely.
router.include_router(
    trip_refunds, prefix="/refunds", tags=["customer-trip-refund-management"]
)

# Trip retrieval endpoints for customers to view their trip details and list their trips. These endpoints will validate the JWT token to ensure that only authenticated customers can access their trip information securely. The view trip details endpoint will allow customers to view the details of a specific trip by providing the booking ID, while the list trips endpoint will enable customers to view a list of all their trips, enhancing the overall user experience and allowing customers to manage their trips effectively.
router.include_router(
    trip_bookings, prefix="/bookings", tags=["customer-trip-retrieval-management"]
)

# Trip type classification endpoint for customers to classify their trips as local or outstation or airport transfer based on the pickup and dropoff locations. This endpoint will validate the JWT token to ensure that only authenticated customers can access this functionality securely. The classification endpoint will allow customers to input their pickup and dropoff locations, and the system will classify the trip type based on predefined criteria, providing customers with insights into their trip classifications and enabling better trip management and planning.
router.include_router(
    trip_type_classifier,
    prefix="/trip-type-classification",
    tags=["customer-trip-type-classification"],
)

# Trip package retrieval endpoints for customers to view available trip packages based on their trip type and region. These endpoints will validate the JWT token to ensure that only authenticated customers can access this information securely. The trip package retrieval endpoint will allow customers to input their trip type and region code, and the system will return a list of available trip packages that match their criteria, enhancing the overall user experience and enabling customers to make informed decisions about their trip options.
router.include_router(
    trip_packages, prefix="/trip-packages", tags=["customer-trip-package-retrieval"]
)

# Fleet browsing endpoint for customers to view the different fleets available in the system which they can then choose from when booking a trip. This endpoint will validate the JWT token to ensure that only authenticated customers can view the available fleets for security reasons.
router.include_router(
    fleet_router, prefix="/fleet", tags=["customer-fleet-browsing"]
)

# Trip support contact retrieval endpoint for customers to get the best support contact based on their trip type and origin location. This endpoint will validate the JWT token to ensure that only authenticated customers can access this functionality securely. The support contact retrieval endpoint will allow customers to input their trip type and origin location, and the system will return the best support contact available for their specific trip, enhancing the overall customer experience and providing timely assistance when needed.
router.include_router(
    trip_support_router, prefix="/support", tags=["customer-trip-support"]
)
