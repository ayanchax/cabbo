from pydantic import BaseModel, Field
from typing import Optional 
from datetime import datetime

class CancelationPolicySchema(BaseModel):
    trip_type_id: str = Field(..., description="ID of the trip type")
    region_id: Optional[str] = Field(None, description="ID of the region for which this cancelation policy applies")
    state_id: Optional[str] = Field(None, description="ID of the state for which this cancelation policy applies")
    free_cutoff_minutes: int = Field(..., description="Free cancellation cutoff in minutes")
    free_cutoff_time_label: Optional[str] = Field(None, description="Label for free cutoff time, e.g., '30 minutes before'")
    refund_percentage: float = Field(..., description="Percentage of the fare to be refunded against advance payment if the cancellation is made on or before the free cutoff time")
    
    effective_from: Optional[datetime] = Field(None, description="DateTime from which this policy is effective")
    effective_to: Optional[datetime] = Field(None, description="DateTime until which this policy is effective")
    is_active: bool = Field(True, description="Indicates if the cancelation policy is active")

    class Config:
        from_attributes = True
 