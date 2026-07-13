from fastapi import APIRouter

from customer_api.src.models.legal_schema import LegalPageRead, LegalPageSummary
from customer_api.src.services.legal_content_service import get_legal_page_by_slug, list_legal_pages


router = APIRouter()


@router.get("/pages", response_model=list[LegalPageSummary])
def get_legal_pages():
    return list_legal_pages()


@router.get("/pages/{slug}", response_model=LegalPageRead)
def get_legal_page(slug: str):
    return get_legal_page_by_slug(slug)
