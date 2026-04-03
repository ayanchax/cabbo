from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_serializer



class CommentSchema(BaseModel):
    id: Optional[str] = Field(None, description="UUID for the comment")
    comment: str = Field(..., description="The content of the comment")
    commented_by: Optional[str] = Field(None, description="User ID of the person who made the comment in the case, it can be support user or the customer")
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Date and time when the comment was created")
    updated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Date and time when the comment was last updated")


    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None