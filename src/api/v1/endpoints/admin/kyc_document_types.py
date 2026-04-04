from sqlalchemy.ext.asyncio import AsyncSession
from api.v1.endpoints.admin.airport import validate_user_token, a_yield_mysql_session
from fastapi import APIRouter, Depends

from core.exceptions import CabboException
from core.security import RoleEnum
from models.documents.kyc_document_schema import (
    KYCDocumentSchema,
    KYCDocumentUpdateSchema,
)
from models.user.user_orm import User
from services.kyc_service import (
    async_activate_kyc_document_record,
    async_add_kyc_document_record,
    async_delete_kyc_document_record,
    async_get_all_kyc_document_records,
    async_get_kyc_document_record_by_id,
    async_update_kyc_document_record,
)

router = APIRouter()


# Add a new kyc document type
@router.post("/add", response_model=KYCDocumentSchema)
async def add_kyc_document_type(
    payload: KYCDocumentSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new KYC document type to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to add KYC document types.", status_code=403
        )
    kyc_document_type, error = await async_add_kyc_document_record(
        payload=payload, db=db, created_by=current_user_role
    )
    if error:
        raise CabboException(error, status_code=400)
    if not kyc_document_type:
        raise CabboException("Failed to add new KYC document type", status_code=500)
    return kyc_document_type


# Get all kyc document types in system
@router.get("/list", response_model=list[KYCDocumentSchema])
async def list_kyc_document_types(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all KYC document types in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view KYC document types.", status_code=403
        )
    kyc_document_types = await async_get_all_kyc_document_records(db)
    return kyc_document_types


# Get a kyc document type by id
@router.get("/{document_id}", response_model=KYCDocumentSchema)
async def get_kyc_document_type_by_id(
    document_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Get a KYC document type by its unique identifier."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to view KYC document types.", status_code=403
        )
    kyc_document_type = await async_get_kyc_document_record_by_id(
        document_id=document_id, db=db
    )
    if not kyc_document_type:
        raise CabboException("KYC document type not found", status_code=404)
    return kyc_document_type


# Update a kyc document type by id
@router.put("/{document_id}", response_model=KYCDocumentSchema)
async def update_kyc_document_type_by_id(
    document_id: str,
    payload: KYCDocumentUpdateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update a KYC document type by its unique identifier."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update KYC document types.", status_code=403
        )
    updated_kyc_document_type, error = await async_update_kyc_document_record(
        document_id=document_id, payload=payload, db=db
    )
    if error:
        raise CabboException(error, status_code=400)
    if not updated_kyc_document_type:
        raise CabboException("Failed to update KYC document type", status_code=500)
    return updated_kyc_document_type


# Delete a kyc document type by id (soft delete by marking is_active=False)
@router.delete("/{document_id}")
async def delete_kyc_document_type_by_id(
    document_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Soft delete a KYC document type by its unique identifier."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete KYC document types.", status_code=403
        )
    success, error = await async_delete_kyc_document_record(
        document_id=document_id, db=db
    )
    if error:
        raise CabboException(error, status_code=400)
    if not success:
        raise CabboException("Failed to delete KYC document type", status_code=500)
    return {"message": "KYC document type deleted successfully"}


# Activate a kyc document type by id (mark is_active=True)
@router.patch("/{document_id}/activate")
async def activate_kyc_document_type_by_id(
    document_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Activate a KYC document type by its unique identifier."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to activate KYC document types.",
            status_code=403,
        )
    success, error = await async_activate_kyc_document_record(
        document_id=document_id, db=db
    )
    if error:
        raise CabboException(error, status_code=400)
    if not success:
        raise CabboException("Failed to activate KYC document type", status_code=500)
    return {"message": "KYC document type activated successfully"}
