from typing import List, Optional
from pydantic import BaseModel

from models.documents.kyc_document_enum import KYCDocumentTypeEnum


class KYCDocumentSchema(BaseModel):
    document_id: Optional[str] = None  # Unique identifier for the document
    document_type: KYCDocumentTypeEnum  # Type of the document (e.g., driver_license, aadhar_card)
    document_url: str  # mount URL to access the document
    document_alias: Optional[str] = None  # Alias for the document type (e.g., Driver License, Aadhar Card)
    document_description: Optional[str] = None  # Description of the document
    verified: bool = False  # Verification status of the document
    extension: Optional[str] = None  # File extension of the document (e.g., .jpg, .pdf)
    size: Optional[int] = None  # Size of the document in bytes

    class Config:
        from_attributes = True
        exclude_none = True

class KYCSchema(BaseModel):
    kyc_documents: Optional[List[KYCDocumentSchema]] = None  # KYC document details (e.g., Driver license, Aadhar card)
    kyc_verified: Optional[bool] = None  # KYC verification status

    class Config:
        exclude_none = True  # Exclude fields with None values from the model dump
        from_attributes = True


