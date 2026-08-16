from pydantic import BaseModel


class LegalPageMetadataInternal(BaseModel):
    slug: str
    title: str
    version: str
    effective_date: str
    content_format: str
    requires_acceptance: bool
    last_updated: str
    status: str
    display_order: int
    category: str
    locale: str


class LegalPageInternal(LegalPageMetadataInternal):
    content: str


class LegalPageSummary(BaseModel):
    slug: str
    title: str
    version: str
    effective_date: str
    requires_acceptance: bool


class LegalPageRead(LegalPageSummary):
    content_format: str
    content: str
