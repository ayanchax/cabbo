from datetime import datetime
from typing import Dict, Optional
from pydantic import BaseModel, Field
from models.policies.refund_enum import RefundStatus, RefundType, RefundTrigger


class RefundSchema(BaseModel):
    id: Optional[str] = Field(None, description="Unique identifier for the refund transaction from the payment provider")
    entity_id: Optional[str] = Field(..., description="ID of the entity for which the refund is being processed, e.g., trip ID, booking ID, etc.")
    policy_id: Optional[str] = Field(None, description="ID of the refund policy that was applied for this refund, if applicable, for example, cancellation policy ID, adjustment policy ID, dispute policy ID etc. This can help us track which kind of policy was applied for this refund and also can be used for reporting and analytics purposes to see which policies are being used more frequently for refunds and also to analyze the effectiveness of different refund policies in terms of customer satisfaction, financial impact, etc.")
    refund_status: Optional[RefundStatus] = Field(RefundStatus.unknown, description="Status of the refund transaction from the payment provider, e.g., pending, completed, failed, etc.")
    refund_amount: float = Field(..., description="Amount to be refunded to the customer")
    refund_reason: str = Field(..., description="Reason for the refund (e.g., cancellation, adjustment, etc.)")
    refund_details: Optional[Dict] = Field(None, description="Details of the refund transaction from the payment provider")
    refund_initiated_datetime: Optional[datetime] = Field(None, description="Date and time when the refund was initiated")
    refund_type: Optional[RefundType] = Field(RefundType.other, description="Type of refund, e.g., full, partial, etc.")
    refund_provider: Optional[str] = Field(None, description="Payment provider used for processing the refund, e.g., Stripe, PayPal, etc.")
    refund_trigger: Optional[RefundTrigger] = Field(RefundTrigger.automatic, description="Description of how the refund was triggered, e.g., 'manual', 'automatic'")