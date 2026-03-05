from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field
from models.support.support_enum import TicketStatusEnum
from models.policies.dispute_enum import DisputeTypeEnum
from models.support.support_schema import SupportCommentSchema


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
    details: Optional[dict] | None = Field(
        None, description="Additional details about the dispute"
    )
    raised_by: str = Field(
        ..., description="User ID of the person who raised the dispute"
    )
    status: TicketStatusEnum = Field(
        TicketStatusEnum.open,
        description="Status of the dispute (e.g., open, resolved, rejected)",
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
