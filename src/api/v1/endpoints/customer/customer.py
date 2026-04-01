from fastapi import (
    APIRouter,
)
from .passenger import router as passenger_router
from .profile import router as profile_router
from .email_verification import router as email_verification_router
router = APIRouter()

#Profile endpoints
router.include_router(profile_router, prefix="/profile", tags=["customer-profile"])

# Email verification endpoints for customers to trigger email verification and verify their email using the verification link sent to their email. These endpoints will validate the JWT token to ensure that only authenticated customers can trigger email verification and verify their email for security reasons. The initiate endpoint will check if the customer's email is already verified or if a verification link has already been sent before creating a new verification link and sending it to the customer's email. The verify endpoint will validate the verification token and mark the customer's email as verified if the token is valid, and also handle edge cases such as expired or invalid tokens gracefully.
router.include_router(email_verification_router, prefix="/email-verification", tags=["customer-email-verification"])

#Passenger management endpoints for customers to manage their passengers which they can then associate with their trip bookings. This will allow customers to easily manage the details of their passengers and associate them with their trips for a smoother booking experience. These endpoints will also validate the JWT token to ensure that only authenticated customers can manage their passengers and that they can only manage passengers associated with their own account for privacy and security reasons.
router.include_router(passenger_router, prefix="/manage-passengers", tags=["passenger-management-for-customers"])

