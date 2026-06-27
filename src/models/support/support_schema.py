from datetime import datetime, timezone
from typing import List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    EmailStr,
    Field,
    field_serializer,
    field_validator,
    model_validator,
)

from models.map.location_schema import LocationInfo
from models.support.support_enum import SupportScopeEnum, SupportTypeEnum
from models.trip.trip_enums import TripTypeEnum



class CommentSchema(BaseModel):
    id: Optional[str] = Field(None, description="UUID for the comment")
    comment: str = Field(..., description="The content of the comment")
    commented_by: Optional[str] = Field(None, description="User ID of the person who made the comment in the case, it can be support user or the customer")
    created_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Date and time when the comment was created")
    updated_at: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc), description="Date and time when the comment was last updated")


    @field_serializer('created_at', 'updated_at')
    def serialize_dt(self, dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None


TripTypeScope = Union[TripTypeEnum, Literal["all"], str]


class SupportRoutingRuleBase(BaseModel):
    scope_type: Optional[SupportScopeEnum] = Field(
        None, description="Geography level where this rule applies"
    )
    scope_id: Optional[str] = Field(
        None, description="ID of the selected country, state, or region"
    )
    country_id: Optional[str] = Field(
        None, description="Country ID when scope_type is country"
    )
    state_id: Optional[str] = Field(
        None, description="State ID when scope_type is state"
    )
    region_id: Optional[str] = Field(
        None, description="Region ID when scope_type is region"
    )
    trip_type_scope: TripTypeScope = Field(
        "all",
        description="Trip type this rule applies to, or 'all' for every trip type",
    )
    priority: int = Field(
        100,
        ge=0,
        description="Lower values win when multiple active support rules match",
    )
    is_active: bool = Field(True, description="Whether this routing rule is active")

    @field_validator("trip_type_scope", mode="before")
    @classmethod
    def normalize_trip_type_scope(cls, value):
        if value is None or value == "":
            return "all"
        if isinstance(value, TripTypeEnum):
            return value.value
        return value

    @model_validator(mode="after")
    def normalize_scope(self):
        geo_values = {
            SupportScopeEnum.country: self.country_id,
            SupportScopeEnum.state: self.state_id,
            SupportScopeEnum.region: self.region_id,
        }
        provided_geographies = [
            scope for scope, value in geo_values.items() if value is not None
        ]

        if self.scope_type and self.scope_id:
            matching_geo_value = geo_values[self.scope_type]
            if matching_geo_value and matching_geo_value != self.scope_id:
                raise ValueError(
                    f"{self.scope_type.value}_id must match scope_id for this scope"
                )
            if self.scope_type == SupportScopeEnum.country:
                self.country_id = self.scope_id
                self.state_id = None
                self.region_id = None
            elif self.scope_type == SupportScopeEnum.state:
                self.country_id = None
                self.state_id = self.scope_id
                self.region_id = None
            elif self.scope_type == SupportScopeEnum.region:
                self.country_id = None
                self.state_id = None
                self.region_id = self.scope_id
            return self

        if len(provided_geographies) != 1:
            raise ValueError(
                "Provide exactly one geography: country_id, state_id, or region_id"
            )

        inferred_scope = provided_geographies[0]
        inferred_scope_id = geo_values[inferred_scope]
        if self.scope_type and self.scope_type != inferred_scope:
            raise ValueError("scope_type does not match the provided geography ID")
        if self.scope_id and self.scope_id != inferred_scope_id:
            raise ValueError("scope_id does not match the provided geography ID")

        self.scope_type = inferred_scope
        self.scope_id = inferred_scope_id
        return self

    class Config:
        from_attributes = True


class SupportRoutingRuleCreate(SupportRoutingRuleBase):
    pass


class SupportRoutingRuleUpdate(BaseModel):
    scope_type: Optional[SupportScopeEnum] = Field(
        None, description="Geography level where this rule applies"
    )
    scope_id: Optional[str] = Field(
        None, description="ID of the selected country, state, or region"
    )
    country_id: Optional[str] = Field(
        None, description="Country ID when scope_type is country"
    )
    state_id: Optional[str] = Field(
        None, description="State ID when scope_type is state"
    )
    region_id: Optional[str] = Field(
        None, description="Region ID when scope_type is region"
    )
    trip_type_scope: Optional[TripTypeScope] = Field(
        None, description="Trip type this rule applies to, or 'all'"
    )
    priority: Optional[int] = Field(
        None,
        ge=0,
        description="Lower values win when multiple active support rules match",
    )
    is_active: Optional[bool] = Field(
        None, description="Whether this routing rule is active"
    )

    @field_validator("trip_type_scope", mode="before")
    @classmethod
    def normalize_trip_type_scope(cls, value):
        if value is None or value == "":
            return value
        if isinstance(value, TripTypeEnum):
            return value.value
        return value

    class Config:
        from_attributes = True


class SupportRoutingRuleSchema(SupportRoutingRuleBase):
    id: Optional[str] = Field(None, description="Unique identifier for the routing rule")
    support_contact_id: Optional[str] = Field(
        None, description="Support contact this routing rule belongs to"
    )
    created_by: Optional[str] = Field(
        None, description="User ID or system actor that created this routing rule"
    )
    created_at: Optional[datetime] = Field(
        None, description="Date and time when the routing rule was created"
    )
    updated_at: Optional[datetime] = Field(
        None, description="Date and time when the routing rule was last updated"
    )


class SupportContactBase(BaseModel):
    display_name: str = Field(..., description="Human-readable support contact name")
    email: EmailStr = Field(..., description="Support email address")
    phone_number: str = Field(
        ..., min_length=6, max_length=20, description="Primary support phone number"
    )
    whatsapp_number: Optional[str] = Field(
        None,
        min_length=6,
        max_length=20,
        description="Optional WhatsApp support number",
    )
    support_type: SupportTypeEnum = Field(
        SupportTypeEnum.customer, description="Support category handled by this contact"
    )
    is_active: bool = Field(True, description="Whether this support contact is active")

    class Config:
        from_attributes = True


class SupportContactCreate(SupportContactBase):
    routing_rules: Optional[List[SupportRoutingRuleCreate]] = Field(
        None, description="Routing rules to create with this contact"
    )


class SupportContactUpdate(BaseModel):
    display_name: Optional[str] = Field(
        None, description="Human-readable support contact name"
    )
    email: Optional[EmailStr] = Field(None, description="Support email address")
    phone_number: Optional[str] = Field(
        None, min_length=6, max_length=20, description="Primary support phone number"
    )
    whatsapp_number: Optional[str] = Field(
        None,
        min_length=6,
        max_length=20,
        description="Optional WhatsApp support number",
    )
    support_type: Optional[SupportTypeEnum] = Field(
        None, description="Support category handled by this contact"
    )
    is_active: Optional[bool] = Field(
        None, description="Whether this support contact is active"
    )
    routing_rules: Optional[List[SupportRoutingRuleCreate]] = Field(
        None,
        description="Optional routing rules to sync or replace for this contact",
    )

    class Config:
        from_attributes = True


class SupportContactSchema(SupportContactBase):
    id: Optional[str] = Field(None, description="Unique identifier for the support contact")
    created_by: Optional[str] = Field(
        None, description="User ID or system actor that created this support contact"
    )
    created_at: Optional[datetime] = Field(
        None, description="Date and time when the support contact was created"
    )
    updated_at: Optional[datetime] = Field(
        None, description="Date and time when the support contact was last updated"
    )
    routing_rules: Optional[List[SupportRoutingRuleSchema]] = Field(
        None, description="Routing rules attached to this support contact"
    )


class CustomerSupportContactSchema(BaseModel):
    display_name: str = Field(..., description="Human-readable support contact name")
    email: EmailStr = Field(..., description="Support email address")
    phone_number: str = Field(..., description="Primary support phone number")
    whatsapp_number: Optional[str] = Field(
        None, description="Optional WhatsApp support number"
    )
    support_type: SupportTypeEnum = Field(
        SupportTypeEnum.customer, description="Support category handled by this contact"
    )

    class Config:
        from_attributes = True


class CustomerSupportContactLookupRequest(BaseModel):
    origin: LocationInfo = Field(
        ..., description="Trip origin geography from the loaded trip details"
    )
    trip_type: TripTypeEnum = Field(
        ..., description="Trip type for resolving support routing"
    )


class SupportContactListSchema(BaseModel):
    items: List[SupportContactSchema] = Field(
        default_factory=list, description="Support contacts returned by the query"
    )
    total: int = Field(0, ge=0, description="Total number of matching support contacts")
    page: Optional[int] = Field(None, ge=1, description="Current page number")
    limit: Optional[int] = Field(None, ge=1, description="Maximum items per page")

    class Config:
        from_attributes = True
