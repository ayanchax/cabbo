from core.constants import APP_NAME
from models.trip.trip_enums import TripStatusEnum


TRIP_MESSAGES = {
    TripStatusEnum.created.value: {
        "messages": {
            "status": TripStatusEnum.created,
            "status_text": "Your trip has been created!",
            "next_steps": [
                {
                    "id": "COMPLETE_ADVANCE_PAYMENT",
                    "step": "Complete Advance Payment",
                    "instruction": "Please complete the advance payment to confirm your trip.",
                    "reason": "This advance payment is our platform/convenience fee that helps us guarantee your trip booking.",
                },
                {
                    "id": "AWAIT_CONFIRMATION",
                    "step": "Await Confirmation",
                    "instruction": "You will receive a confirmation once the payment is successful.",
                },
            ],
        }
    },
    TripStatusEnum.confirmed.value: {
        "messages": {
            "status": TripStatusEnum.confirmed,
            "status_text": "Your booking has been confirmed!",
            "next_steps": [
                {
                    "id": "AWAIT_TRIP_DETAILS",
                    "step": "Await trip details",
                    "instruction": "Your booking is confirmed! You will receive the trip and driver details in your registered email shortly. You can also view all your trip details anytime in the app.",
                },
                {
                    "id": "PAY_REMAINING_FARE",
                    "step": "Pay remaining fare after trip completion",
                    "instruction": "You will receive an invoice after your trip ends, and you should pay the rest of your fare only through the app or provided payment link in the invoice.",
                },
            ],
            "advisory": [
                {
                    "id": "DO_NOT_PAY_FOR_DRIVER_ACCOMMODATION",
                    "instruction": "You are not required or liable to arrange or pay for any driver accommodation.",
                    "additional_info": f"If you are willing to provide driver accommodation during the trip, please do so at your own discretion and {APP_NAME.capitalize()} will not be responsible for any such arrangements.",
                },
                {
                    "id": "DO_NOT_PAY_FOR_DRIVER_FOOD",
                    "instruction": "You are not required or liable to arrange or pay for any driver food or meals.",
                    "additional_info": f"If you are willing to provide driver food or meals during the trip, please do so at your own discretion and {APP_NAME.capitalize()} will not be responsible for any such arrangements.",
                },
                {
                    "id": "DO_NOT_PAY_TO_DRIVER",
                    "instruction": "Please do not make any trip related payments to the driver directly.",
                    "additional_info": "All trip related payments should be made through the app for your safety.",
                },
                {
                    "id": "DO_NOT_ENTERTAIN_PAYMENT_REQUESTS_FROM_DRIVER",
                    "instruction": "Please do not entertain any kind of payment requests from the driver.",
                    "additional_info": "All payment requests should be directed through the app for your safety. If the driver insists, please report it to our support team.",
                },
                {
                    "id": "OPTIONAL_TIPPING",
                    "instruction": "You are free to tip your driver directly in cash/UPI, at your own discretion.",
                    "additional_info": "Tipping is not mandatory but greatly appreciated.",
                },
                {
                    "id": "CONTACT_SUPPORT_GENERAL",
                    "instruction": f"If you face any issues or have concerns during your trip, please contact {APP_NAME.capitalize()} support immediately.",
                    "additional_info": "Your comfort and safety are our priority. Our support team is always here to help you.",
                },
            ],
        }
    },
}

COMMON_INCLUSIONS = [
    "Base fare",
    "Premium AC cab with professional driver",
    "Doorstep pickup and drop",
    "Platform/Convenience fee",
    "Well-maintained and sanitized vehicle",
    "24/7 customer support",
]

COMMON_EXCLUSIONS = [
    "Personal expenses",
    "Self sponsored driver meals",
    "Tolls(if applicable)",
    "Extra parking(if any)",
]
