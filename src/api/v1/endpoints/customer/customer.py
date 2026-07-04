from fastapi import (
    APIRouter,
)
from .passenger import router as passenger_router
from .profile import router as profile_router
from .email_verification import router as email_verification_router
from .recent_locations import router as recent_locations_router
router = APIRouter()

#Profile endpoints
router.include_router(profile_router, prefix="/profile", tags=["customer-profile"])

# Email verification endpoints for customers to trigger email verification and verify their email using the verification link sent to their email. The initiate endpoint requires an authenticated customer. The verify endpoint is public because the verification link token proves access to the customer's email inbox, which allows verification even if the customer opens the link from a different browser or logged-out session.
router.include_router(email_verification_router, prefix="/email-verification", tags=["customer-email-verification"])

#Passenger management endpoints for customers to manage their passengers which they can then associate with their trip bookings. This will allow customers to easily manage the details of their passengers and associate them with their trips for a smoother booking experience. These endpoints will also validate the JWT token to ensure that only authenticated customers can manage their passengers and that they can only manage passengers associated with their own account for privacy and security reasons.
router.include_router(passenger_router, prefix="/manage-passengers", tags=["passenger-management-for-customers"])

# Recent locations endpoints for customers to view and manage their recent pickup and dropoff locations which they can then associate with their trip bookings. This will allow customers to easily manage their frequently used locations and associate them with their trips for a smoother booking experience. These endpoints will also validate the JWT token to ensure that only authenticated customers can manage their recent locations and that they can only manage recent locations associated with their own account for privacy and security reasons.
router.include_router(recent_locations_router, prefix="/recent-locations", tags=["recent-locations-for-customers"])

