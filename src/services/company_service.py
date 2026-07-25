from core.company_info import PUBLIC_COMPANY_INFO
from models.company_schema import PublicCompanyInfo


def get_public_company_info() -> PublicCompanyInfo:
    return PublicCompanyInfo(**PUBLIC_COMPANY_INFO)
