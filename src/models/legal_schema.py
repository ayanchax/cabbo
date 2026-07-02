from pydantic import BaseModel


class LegalPageMetadata(BaseModel):
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


class LegalPageRead(LegalPageMetadata):
    content: str
