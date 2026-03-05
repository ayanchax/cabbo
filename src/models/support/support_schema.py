from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SupportCommentSchema(BaseModel):
    id: Optional[str] = Field( )  # UUID for the support comment
    ticket_id: str = Field(..., description="ID of the associated support ticket")
    comment: str = Field(..., description="The content of the support comment")
    commented_by: str = Field(..., description="User ID of the person who made the comment in the case, it can be support user or the customer")
    created_at: Optional[datetime] = Field(None, description="Date and time when the comment was created")
    updated_at: Optional[datetime] = Field(None, description="Date and time when the comment was last updated")