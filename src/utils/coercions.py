from datetime import date, datetime
from typing import Union
from typing import Optional

from core.exceptions import GENERIC_EXCEPTION, CabboException
from models.policies.refund_enum import RefundStatus
from models.trip.trip_enums import CancellationSubStatusEnum, CarTypeEnum, FuelTypeEnum, TripStatusEnum, TripTypeEnum


def coerce_car_type(value) -> Optional[CarTypeEnum]:
    if not value:
        return None
    if isinstance(value, CarTypeEnum):
        return value
    try:
        return CarTypeEnum(value)
    except ValueError:
        return CarTypeEnum[str(value)]


def coerce_fuel_type(value) -> Optional[FuelTypeEnum]:
    if not value:
        return None
    if isinstance(value, FuelTypeEnum):
        return value
    try:
        return FuelTypeEnum(value)
    except ValueError:
        return FuelTypeEnum[str(value)]


def coerce_cancellation_sub_status(status: Optional[Union[str, CancellationSubStatusEnum]]) -> Optional[CancellationSubStatusEnum]:
    if not status:
        return None
    if isinstance(status, CancellationSubStatusEnum):
        return status
    try:
        return CancellationSubStatusEnum(status)
    except ValueError:
        return None
    
def coerce_refund_status(status: Optional[Union[str, RefundStatus]]) -> Optional[RefundStatus]:
    if not status:
        return None
    if isinstance(status, RefundStatus):
        return status
    try:
        return RefundStatus(status)
    except ValueError:
        return None

def coerce_trip_status(status: Optional[Union[str, TripStatusEnum]]) -> Optional[TripStatusEnum]:
    if not status:
        return None
    if isinstance(status, TripStatusEnum):
        return status
    try:
        return TripStatusEnum(status)
    except ValueError:
        return None


def coerce_trip_type(trip_type: Optional[Union[str, TripTypeEnum]]) -> Optional[TripTypeEnum]:
    if not trip_type:
        return None
    if isinstance(trip_type, TripTypeEnum):
        return trip_type
    try:
        return TripTypeEnum(trip_type)
    except ValueError:
        return None



    
def coerce_trip_filter_date(
    value: Optional[Union[date, str]], field_name: str
) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            raise CabboException(
                f"Invalid {field_name}. Expected date in YYYY-MM-DD format.",
                status_code=400,
                error_code=GENERIC_EXCEPTION,
            )
    raise CabboException(
        f"Invalid {field_name}. Expected date in YYYY-MM-DD format.",
        status_code=400,
        error_code=GENERIC_EXCEPTION,
    )
