from typing import Union

from core.exceptions import (
    INVALID_TRIP_STATUS_TRANSITION,
    UNAUTHORIZED,
    CabboException,
    GENERIC_EXCEPTION,
)
from core.security import RoleEnum
from models.customer.customer_orm import Customer
from models.policies.dispute_enum import DisputeTypeEnum
from models.trip.trip_enums import CancellationSubStatusEnum, TripStatusEnum
from models.trip.trip_orm import Trip
from models.trip.trip_schema import (
    TripStatusPayloadFieldTypeEnum,
    TripStatusTransitionAction,
    TripStatusTransitionPayloadField,
)
from models.user.user_orm import User

ALLOWED_STATUS_TRANSITIONS: dict[TripStatusEnum, list[TripStatusEnum]] = {
    TripStatusEnum.confirmed: [TripStatusEnum.ongoing, TripStatusEnum.cancelled],
    TripStatusEnum.ongoing: [TripStatusEnum.completed, TripStatusEnum.dispute],
    TripStatusEnum.completed: [],
    TripStatusEnum.cancelled: [],
    TripStatusEnum.dispute: [],
}

ADMIN_STATUS_ACTION_ROLES = {RoleEnum.super_admin, RoleEnum.driver_admin}


TRANSITION_ACTIONS: dict[TripStatusEnum, TripStatusTransitionAction] = {
    TripStatusEnum.ongoing: TripStatusTransitionAction(
        target_status=TripStatusEnum.ongoing,
        label="Start trip",
        requires_confirmation=True,
        confirmation_level="light",
        payload_fields=[
            TripStatusTransitionPayloadField(
                name="reason",
                type=TripStatusPayloadFieldTypeEnum.string,
                required=False,
                label="Reason",
            ),
            TripStatusTransitionPayloadField(
                name="start_datetime",
                type=TripStatusPayloadFieldTypeEnum.datetime,
                required=False,
                label="Actual start time",
            ),
        ],
    ),
    TripStatusEnum.completed: TripStatusTransitionAction(
        target_status=TripStatusEnum.completed,
        label="Complete trip",
        requires_confirmation=True,
        confirmation_level="standard",
        payload_fields=[
            TripStatusTransitionPayloadField(
                name="reason",
                type=TripStatusPayloadFieldTypeEnum.string,
                required=False,
                label="Reason",
            ),
            TripStatusTransitionPayloadField(
                name="end_datetime",
                type=TripStatusPayloadFieldTypeEnum.datetime,
                required=False,
                label="Actual end time",
            ),
            TripStatusTransitionPayloadField(
                name="extra_payment_to_driver",
                type=TripStatusPayloadFieldTypeEnum.object,
                required=False,
                label="Extra payment to driver",
                description="Optional tolls, parking, overage, tips, and notes.",
                fields=[
                    TripStatusTransitionPayloadField(
                        name="extra_payment_to_driver.toll_charges",
                        type=TripStatusPayloadFieldTypeEnum.number,
                        required=False,
                        label="Toll charges",
                        description="Toll charges paid by driver during the trip",
                    ),
                    TripStatusTransitionPayloadField(
                        name="extra_payment_to_driver.parking_charges",
                        type=TripStatusPayloadFieldTypeEnum.number,
                        required=False,
                        label="Parking charges",
                        description="Parking charges paid by driver during the trip",
                    ),
                    TripStatusTransitionPayloadField(
                        name="extra_payment_to_driver.overage_payment",
                        type=TripStatusPayloadFieldTypeEnum.number,
                        required=False,
                        label="Overage payment",
                        description="Payment to driver for extra distance or time beyond estimate",
                    ),
                    TripStatusTransitionPayloadField(
                        name="extra_payment_to_driver.tips",
                        type=TripStatusPayloadFieldTypeEnum.number,
                        required=False,
                        label="Tips",
                        description="Tips or incentive payment provided to driver",
                    ),
                    TripStatusTransitionPayloadField(
                        name="extra_payment_to_driver.comments",
                        type=TripStatusPayloadFieldTypeEnum.string,
                        required=False,
                        label="Comments",
                    ),
                ],
            ),
        ],
    ),
    TripStatusEnum.cancelled: TripStatusTransitionAction(
        target_status=TripStatusEnum.cancelled,
        label="Cancel trip",
        requires_confirmation=True,
        confirmation_level="strong",
        payload_fields=[
            TripStatusTransitionPayloadField(
                name="reason",
                type=TripStatusPayloadFieldTypeEnum.string,
                required=True,
                label="Reason",
            ),
            TripStatusTransitionPayloadField(
                name="cancelation_detail.cancellation_sub_status",
                type=TripStatusPayloadFieldTypeEnum.enum,
                required=True,
                label="Cancellation sub-status",
                options=[
                    status.value
                    for status in CancellationSubStatusEnum
                    if status
                    not in [
                        CancellationSubStatusEnum.none,
                        CancellationSubStatusEnum.customer_cancelled,
                    ]
                ],
            ),
        ],
    ),
    TripStatusEnum.dispute: TripStatusTransitionAction(
        target_status=TripStatusEnum.dispute,
        label="Move to dispute",
        requires_confirmation=True,
        confirmation_level="strong",
        payload_fields=[
            TripStatusTransitionPayloadField(
                name="reason",
                type=TripStatusPayloadFieldTypeEnum.string,
                required=True,
                label="Reason",
            ),
            TripStatusTransitionPayloadField(
                name="dispute_detail",
                type=TripStatusPayloadFieldTypeEnum.object,
                required=True,
                label="Dispute details",
                fields=[
                    TripStatusTransitionPayloadField(
                        name="dispute_detail.reason",
                        type=TripStatusPayloadFieldTypeEnum.string,
                        required=False,
                        label="Dispute reason",
                    ),
                    TripStatusTransitionPayloadField(
                        name="dispute_detail.dispute_type",
                        type=TripStatusPayloadFieldTypeEnum.enum,
                        required=True,
                        label="Dispute type",
                        options=[
                            dispute_type.value
                            for dispute_type in DisputeTypeEnum
                            if dispute_type != DisputeTypeEnum.unknown
                        ],
                    ),
                    TripStatusTransitionPayloadField(
                        name="dispute_detail.details",
                        type=TripStatusPayloadFieldTypeEnum.object,
                        required=False,
                        label="Structured details",
                        fields=[
                            TripStatusTransitionPayloadField(
                                name="dispute_detail.details.fare",
                                type=TripStatusPayloadFieldTypeEnum.object,
                                required=False,
                                label="Fare dispute details",
                                fields=[
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.fare.estimated_fare",
                                        type=TripStatusPayloadFieldTypeEnum.number,
                                        required=False,
                                        label="Estimated fare",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.fare.final_fare",
                                        type=TripStatusPayloadFieldTypeEnum.number,
                                        required=False,
                                        label="Final fare",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.fare.extra_distance_km",
                                        type=TripStatusPayloadFieldTypeEnum.number,
                                        required=False,
                                        label="Extra distance",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.fare.disputed_amount",
                                        type=TripStatusPayloadFieldTypeEnum.number,
                                        required=False,
                                        label="Disputed amount",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.fare.customer_claim",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Customer claim",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.fare.driver_claim",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Driver claim",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.fare.support_notes",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Support notes",
                                    ),
                                ],
                            ),
                            TripStatusTransitionPayloadField(
                                name="dispute_detail.details.service",
                                type=TripStatusPayloadFieldTypeEnum.object,
                                required=False,
                                label="Service dispute details",
                                fields=[
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.service.incident_location",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Incident location",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.service.customer_complaint",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Customer complaint",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.service.driver_version",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Driver version",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.service.support_notes",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Support notes",
                                    ),
                                ],
                            ),
                            TripStatusTransitionPayloadField(
                                name="dispute_detail.details.other",
                                type=TripStatusPayloadFieldTypeEnum.object,
                                required=False,
                                label="Other dispute details",
                                fields=[
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.other.description",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Description",
                                    ),
                                    TripStatusTransitionPayloadField(
                                        name="dispute_detail.details.other.support_notes",
                                        type=TripStatusPayloadFieldTypeEnum.string,
                                        required=False,
                                        label="Support notes",
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    ),
}


def _coerce_trip_status(status: Union[str, TripStatusEnum]) -> TripStatusEnum:
    return status if isinstance(status, TripStatusEnum) else TripStatusEnum(status)


def get_allowed_target_statuses(
    current_status: Union[str, TripStatusEnum],
) -> list[TripStatusEnum]:
    status = _coerce_trip_status(current_status)
    return ALLOWED_STATUS_TRANSITIONS.get(status, [])


def get_allowed_trip_status_transitions(
    trip: Trip,
    current_user: User,
) -> list[dict]:
    if current_user.role not in ADMIN_STATUS_ACTION_ROLES:
        return []

    target_statuses = get_allowed_target_statuses(trip.status)
    return [
        TRANSITION_ACTIONS[target_status].model_dump(mode="json", exclude_none=True)
        for target_status in target_statuses
    ]


def validate_trip_status_transition(
    trip: Trip,
    new_status: TripStatusEnum,
    requestor: Union[User, Customer],
) -> None:
    current_status = _coerce_trip_status(trip.status)
    if isinstance(requestor, User) and requestor.role not in ADMIN_STATUS_ACTION_ROLES:
        raise CabboException(
            "You do not have permission to update trip status.",
            status_code=403,
            error_code=UNAUTHORIZED,
        )

    if new_status not in get_allowed_target_statuses(current_status):
        raise CabboException(
            f"Invalid status transition from {current_status.value} to {new_status.value}.",
            status_code=400,
            error_code=INVALID_TRIP_STATUS_TRANSITION,
        )
