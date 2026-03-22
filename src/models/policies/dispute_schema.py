from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from models.support.support_enum import TicketStatusEnum
from models.policies.dispute_enum import DisputeTypeEnum, DisputeTriggerEnum
from models.support.support_schema import SupportCommentSchema


class FareDisputeDetails(BaseModel):
    estimated_fare: Optional[float] = None
    final_fare: Optional[float] = None
    extra_distance_km: Optional[float] = (
        None  # overage distance beyond the original trip distance
    )
    disputed_amount: Optional[float] = None
    # payment evidence fields fit naturally here too
    customer_claim: Optional[str] = None
    driver_claim: Optional[str] = None
    support_notes: Optional[str] = None


class ServiceDisputeDetails(BaseModel):
    incident_location: Optional[str] = None
    customer_complaint: Optional[str] = None
    driver_version: Optional[str] = None  # driver's account of events
    support_notes: Optional[str] = None


class OtherDisputeDetails(BaseModel):
    """Catch-all for 'other' and 'unknown' types."""

    description: Optional[str] = None
    support_notes: Optional[str] = None

    class Config:
        extra = "allow"  # allow freeform fields only for the unstructured types


class DisputeDetailsSchema(BaseModel):
    """Structured details for different dispute types. Only relevant fields will be populated based on the dispute_type."""

    fare: Optional[FareDisputeDetails] = None
    service: Optional[ServiceDisputeDetails] = None
    other: Optional[OtherDisputeDetails] = None


class DisputeSchema(BaseModel):
    id: Optional[str] = Field(None, description="UUID for the dispute")
    entity_id: str = Field(..., description="ID of the associated trip")
    reason: Optional[str] = Field(None, description="Reason for the dispute")
    dispute_type: DisputeTypeEnum | None = Field(
        DisputeTypeEnum.other, description="Type of dispute, e.g., fare, service, etc."
    )
    comments: Optional[List[SupportCommentSchema]] | List[dict] | None = Field(
        None,
        description="Additional comments or details between customer and support regarding the dispute",
    )
    details: Optional[DisputeDetailsSchema] | None = Field(
        None, description="Additional details about the dispute"
    )
    raised_by: str = Field(
        ..., description="User ID of the person who raised the dispute"
    )
    status: TicketStatusEnum = Field(
        TicketStatusEnum.open,
        description="Status of the dispute (e.g., open, resolved, rejected)",
    )
    dispute_trigger: Optional[DisputeTriggerEnum] = Field(
        DisputeTriggerEnum.automatic,
        description="Description of how the dispute was triggered, e.g., 'manual', 'automatic'",
    )
    created_at: Optional[datetime] = Field(
        None, description="Date and time when the dispute was created"
    )
    updated_at: Optional[datetime] = Field(
        None, description="Date and time when the dispute was last updated"
    )
    is_active: bool = Field(
        True,
        description="Flag to indicate if the dispute record is active or has been soft-deleted",
    )

    class Config:
        extra = "allow"
        from_attributes = True


class InitialDisputeSchema(BaseModel):
    reason: Optional[str] = Field(None, description="Reason for the dispute")

    dispute_type: DisputeTypeEnum | None = Field(
        DisputeTypeEnum.other, description="Type of dispute, e.g., fare, service, etc."
    )
    comments: Optional[List[SupportCommentSchema]] | List[dict] | None = Field(
        None,
        description="Additional comments or details between customer and support regarding the dispute",
    )
    details: Optional[DisputeDetailsSchema] | None = Field(
        None, description="Additional details about the dispute"
    )
