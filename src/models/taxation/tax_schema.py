from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaxConfigurationSchema(BaseModel):
    id: Optional[str] = None
    country_id: str
    tax_type: str = Field("GST", description="Tax family, e.g. GST")
    tax_scope: str = Field(..., description="Taxable charge scope, e.g. platform_fee,ride_fee")
    rate_percent: float = Field(..., description="Tax rate percentage")
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    is_active: bool = True

    class Config:
        from_attributes = True
