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
                    "id": "PAY_REMAINING_FARE_TO_DRIVER",
                    "step": "Pay remaining fare to driver after trip completion",
                    "instruction": "After your trip is completed, please pay the remaining fare shown in the app, along with any additional charges such as tolls, paid parking, extra hours/kilometres, or night surcharges directly to the driver in cash/UPI.",
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
                    "id": "DO_NOT_ENTERTAIN_UNWANTED_PAYMENT_REQUESTS_FROM_DRIVER",
                    "instruction": "Please do not pay any money to the driver outside of the trip fare and applicable additional charges.",
                    "additional_info": "You are only required to pay the remaining fare shown in the app and any applicable additional charges such as tolls, paid parking, extra hours/kilometres, or night surcharges. If the driver requests any other payments, please report it to our support team immediately.",
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
    "Paid parking(if applicable)",
]
