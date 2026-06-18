import math

from core.store import ConfigStore
from models.policies.cancelation_schema import CancelationPolicySchema
from models.trip.trip_enums import TripTypeEnum
import logging
log = logging.getLogger(__name__)

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
    
def get_refund_and_cancellation_policy_lines(policy:CancelationPolicySchema):
    
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
        lines.append(
            f"Full refund if you cancel atleast {policy.free_cutoff_time_label}."
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