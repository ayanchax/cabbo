from pydantic import BaseModel


class PublicCompanyInfo(BaseModel):
    legal_name: str
    brand_name: str
    cin: str
    gstin: str
