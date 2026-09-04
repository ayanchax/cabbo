from datetime import datetime, timezone
import logging
from typing import Optional
from core.exceptions import (
    UPGRADE_NOT_ALLOWED,
    CabboException,
)
from models.driver.driver_orm import Driver

from models.trip.trip_enums import (
    CarTypeEnum,
    FuelTypeEnum,
)
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripUpgradationInformationSchema,
)
from models.user.user_orm import User

from utils.coercions import coerce_car_type, coerce_fuel_type

log = logging.getLogger(__name__)

ALLOWED_FUEL_UPGRADES = {
    (FuelTypeEnum.petrol, FuelTypeEnum.hybrid),
    (FuelTypeEnum.cng, FuelTypeEnum.hybrid),
    (FuelTypeEnum.hybrid, FuelTypeEnum.diesel),
    (FuelTypeEnum.cng, FuelTypeEnum.diesel),
}

ALLOWED_CAB_TYPE_UPGRADES = {
    (CarTypeEnum.hatchback, CarTypeEnum.sedan),
    (CarTypeEnum.sedan, CarTypeEnum.sedan_plus),
    (CarTypeEnum.suv, CarTypeEnum.suv_plus),
}


def _format_enum_value(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _format_fuel_value(value) -> str:
    fuel_labels = {
        FuelTypeEnum.cng: "CNG",
        FuelTypeEnum.hybrid: "Hybrid",
        FuelTypeEnum.diesel: "Diesel",
        FuelTypeEnum.petrol: "Petrol",
    }
    return fuel_labels.get(coerce_fuel_type(value), _format_enum_value(value))


def _format_car_value(value) -> str:
    car_labels = {
        CarTypeEnum.hatchback: "Hatchback",
        CarTypeEnum.sedan: "Sedan",
        CarTypeEnum.sedan_plus: "Premium Sedan",
        CarTypeEnum.suv: "SUV",
        CarTypeEnum.suv_plus: "SUV+",
    }
    return car_labels.get(coerce_car_type(value), _format_enum_value(value))


def build_trip_upgradation_information(
    trip: Trip,
    driver: Driver,
    requestor: User,
    reason: str = "free_upgradation",
) -> Optional[TripUpgradationInformationSchema]:
    preferred_car_type = coerce_car_type(trip.preferred_car_type)
    assigned_car_type = coerce_car_type(driver.cab_type)
    preferred_fuel_type = coerce_fuel_type(trip.preferred_fuel_type)
    assigned_fuel_type = coerce_fuel_type(driver.fuel_type)

    upgrade_types = []
    invalid_reasons = []

    if (
        preferred_car_type
        and assigned_car_type
        and preferred_car_type != assigned_car_type
    ):
        if (preferred_car_type, assigned_car_type) in ALLOWED_CAB_TYPE_UPGRADES:
            upgrade_types.append("cab_type_upgrade")
        else:
            invalid_reasons.append(
                f"cab type {preferred_car_type.value} -> {assigned_car_type.value}"
            )

    if (
        preferred_fuel_type
        and assigned_fuel_type
        and preferred_fuel_type != assigned_fuel_type
    ):
        if (preferred_fuel_type, assigned_fuel_type) in ALLOWED_FUEL_UPGRADES:
            upgrade_types.append("fuel_upgrade")
        else:
            invalid_reasons.append(
                f"fuel type {preferred_fuel_type.value} -> {assigned_fuel_type.value}"
            )

    if invalid_reasons:
        # We won't allow a driver assignment that downgrades or mismatches the customer's booked cab preference. Raise an exception with the reasons.
        raise CabboException(
            "Driver assignment would downgrade or mismatch the customer's booked cab preference: "
            + ", ".join(invalid_reasons),
            status_code=400,
            error_code=UPGRADE_NOT_ALLOWED,
        )

    if not upgrade_types:
        return None

    from_label_parts = [
        _format_fuel_value(preferred_fuel_type) if preferred_fuel_type else None,
        _format_car_value(preferred_car_type) if preferred_car_type else None,
    ]
    to_label_parts = [
        _format_fuel_value(assigned_fuel_type) if assigned_fuel_type else None,
        _format_car_value(assigned_car_type) if assigned_car_type else None,
    ]

    from_label = " ".join(part for part in from_label_parts if part)
    to_label = " ".join(part for part in to_label_parts if part)
    short_text = f"Upgraded to {to_label} at no extra charge" #Example: "Upgraded to Diesel SUV at no extra charge"
    long_text = (
    f"Your booked preference was {from_label}. "
    f"Cabbo upgraded you to {to_label} at no extra charge."
)   #Example: "Your booked preference was Hybrid Hatchback. Cabbo upgraded you to Diesel Sedan at no extra charge."

    
    return TripUpgradationInformationSchema(
        upgraded=True,
        upgrade_types=upgrade_types,
        from_cab_type=preferred_car_type,
        from_fuel_type=preferred_fuel_type,
        to_cab_type=assigned_car_type,
        to_fuel_type=assigned_fuel_type,
        additional_charges=0.0,
        short_text=short_text,
        long_text=long_text,
        reason=reason,
        is_free_upgradation=True,
        upgradation_timestamp=datetime.now(timezone.utc),
        upgraded_by_id=requestor.id if requestor else None,
    )

def serialize_trip_upgradtion(trip_dict: dict) -> Optional[dict]:
    upgradation_information = trip_dict.get("upgradation_information", None)
    if not upgradation_information:
        return None
    exclude_fields = ["upgraded_by_id", "upgradation_timestamp", "short_text", "long_text", "reason", "upgrade_types", "additional_charges"]
    return TripUpgradationInformationSchema(**upgradation_information).model_dump(exclude_none=True, exclude=exclude_fields)

