from fastapi import APIRouter

from models.company_schema import PublicCompanyInfo
from services.company_service import get_public_company_info


router = APIRouter()


@router.get("", response_model=PublicCompanyInfo)
def get_company_info():
    return get_public_company_info()
