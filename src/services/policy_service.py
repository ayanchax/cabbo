from datetime import datetime, timedelta
import math
from typing import Union

from core.store import ConfigStore
from models.map.location_schema import LocationInfo
from models.policies.cancelation_schema import CancelationPolicySchema
from models.trip.trip_enums import TripTypeEnum
import logging
from core.config import settings
from models.trip.trip_orm import Trip
from utils.utility import as_utc_datetime, format_trip_datetime, validate_date_time

log = logging.getLogger(__name__)


def _format_refund_cutoff_datetime(cutoff_datetime: datetime) -> str:
    hour = cutoff_datetime.hour % 12 or 12
    meridiem = "AM" if cutoff_datetime.hour < 12 else "PM"
    return (
        f"{cutoff_datetime:%b} {cutoff_datetime.day} {cutoff_datetime.year} "
        f"{hour}:{cutoff_datetime.minute:02d} {meridiem}"
    )


def _trip_start_datetime_as_utc(
    trip_startdate_time: Union[str, datetime]
) -> datetime:
    if isinstance(trip_startdate_time, datetime):
        return as_utc_datetime(trip_startdate_time)

    return validate_date_time(date_time=trip_startdate_time, timezone_str="UTC")


def get_refund_and_cancellation_policy_by_jurisdiction_code(trip_type: TripTypeEnum, config_store: ConfigStore, jurisdiction_code: str):
    trip_type_id = next(tt.id for tt in config_store.trip_types if tt.trip_type == trip_type)
    if not trip_type_id:
        log.info(
                    f"Trip type {trip_type.value} not found in config store trip types, cannot fetch cancellation policy for trip type {trip_type.value} and jurisdiction code {jurisdiction_code}"
                )
        return None
    if trip_type ==TripTypeEnum.local:
        return config_store.local.get(
                            jurisdiction_code
                        ).auxiliary_pricing.cancellation_policy.get(
                            trip_type_id
                        )
    elif trip_type ==TripTypeEnum.airport_pickup:
        return config_store.airport_pickup.get(
                            jurisdiction_code
                        ).auxiliary_pricing.cancellation_policy.get(
                            trip_type_id
                        )
    elif trip_type ==TripTypeEnum.airport_drop:
        return config_store.airport_drop.get(
                            jurisdiction_code
                        ).auxiliary_pricing.cancellation_policy.get(
                            trip_type_id
                        )
    elif trip_type == TripTypeEnum.outstation:
        return config_store.outstation.get(
                        jurisdiction_code
                    ).auxiliary_pricing.cancellation_policy.get(
                        trip_type_id
                    )
    else:
        log.info(
                    f"Trip type {trip_type.value} not eligible for cancellation refund"
                )
        return None

def get_refund_and_cancellation_policy_lines(
    policy: CancelationPolicySchema,
    trip_startdate_time: Union[str, datetime] = None,
    trip_timezone: str = None,
):
    
    if not policy:
        # Give some default lines about contacting support for refund and cancellation queries if policy is not defined for the region/trip type, to ensure we are not leaving users without any information
        default_lines = [
            "For any refund or cancellation queries, please contact Cabbo support. We are committed to transparent and fair policies.",
            "Refund and cancellation policies may vary based on your trip type and region. Please refer to your booking details or contact support for specific information regarding your trip."
        ]   
        return default_lines

    lines = []
    # 1. Full refund if cancelled before cutoff
    if policy.free_cutoff_minutes and policy.free_cutoff_time_label:
        if trip_startdate_time and trip_timezone:
            trip_startdate_time_in_utc = _trip_start_datetime_as_utc(
                trip_startdate_time=trip_startdate_time,
            )
            exact_date_time_upto_which_full_refund_can_be_availed_in_utc = (
                trip_startdate_time_in_utc - timedelta(minutes=policy.free_cutoff_minutes)
            )
            exact_date_time_upto_which_full_refund_can_be_availed = (
                format_trip_datetime(
                    exact_date_time_upto_which_full_refund_can_be_availed_in_utc,
                    trip_timezone,
                )
            )
            full_refund_cutoff_label = _format_refund_cutoff_datetime(
                exact_date_time_upto_which_full_refund_can_be_availed
            )
            lines.append(
                f"Full refund if you cancel by {full_refund_cutoff_label}."
            )
        else:
            lines.append(
                f"Full refund if you cancel at least {policy.free_cutoff_time_label}."
            )
    # 2. Partial refund if cancelled after cutoff
    if policy.refund_percentage is not None and policy.refund_percentage < 100:
        rounded_refund_percentage = int(math.ceil(policy.refund_percentage))
        lines.append(
            f"If you cancel after this period, {rounded_refund_percentage}% of the paid amount will be refunded."
        )
    # 3. Full refund for Cabbo operational issues
    lines.append(
        "Full refund if your trip could not be fulfilled due to Cabbo operational issues (e.g., no driver assigned, vehicle breakdown before trip start, or force majeure events)."
    )
    # 4. Instant refund processing
    lines.append(
        "Refunds are processed instantly upon cancellation confirmation. Depending on your payment method, it may take 1-3 business days for the amount to reflect in your source account."
    )
    # 5. Transparency and support
    lines.append(
        "For any refund or cancellation queries, please contact Cabbo support. We are committed to transparent and fair policies."
    )
    return lines

def serialize_cancellation_and_refund_policy(
    trip: Trip, trip_dict: dict, trip_type: TripTypeEnum,
):
    config_store = settings.get_config_store()
    origin = LocationInfo.model_validate(trip.origin) if trip.origin else None
    if origin:
        # We do not save cancellation or refund policy in trip table as a column
        # We instead fetch the cancellation and refund policy based on the trip type and origin location of the trip at the time of serializing the trip details for response, so that we always provide the most up to date cancellation and refund policy information in the response based on the current policies defined for the region/state and trip type, without having to worry about keeping the cancellation and refund policy information in sync in case of any policy updates in the future.
        # This also ensures we are not storing redundant information in our database and only fetching the relevant latest and greatest cancellation and refund policy information when needed for response serialization.
        jurisdiction_code = (
            origin.region_code
            if trip_type
            in [
                TripTypeEnum.local,
                TripTypeEnum.airport_pickup,
                TripTypeEnum.airport_drop,
            ]
            else origin.state_code
        )  # For local trips and airport trips, cancellation policy is based on region code, for outstation trips, it's based on state code
        cancelation_refund_policy = (
            get_refund_and_cancellation_policy_by_jurisdiction_code(
                trip_type=trip_type,
                jurisdiction_code=jurisdiction_code,
                config_store=config_store,
            )
        )  # Ensure refund policy exists for local trips in the region
        refund_and_cancellation_policy = get_refund_and_cancellation_policy_lines(
            policy=cancelation_refund_policy,
            trip_startdate_time=trip.start_datetime,
            trip_timezone=trip.timezone,
        )
        trip_dict["refund_and_cancellation_policy"] = refund_and_cancellation_policy
    return trip_dict
