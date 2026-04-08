from uuid import uuid4
from core.exceptions import CabboException
from core.security import RoleEnum
from models.documents.kyc_document_enum import KYCDocumentTypeEnum
from models.documents.kyc_document_orm import KYCDocumentTypes
from sqlalchemy.orm import Session
import os
from fastapi import UploadFile
from models.documents.kyc_document_schema import KYCDocumentSchema, KYCDocumentTypeSchema, KYCDocumentUpdateSchema
from models.driver.driver_orm import Driver
from services.file_service import remove_driver_kyc_document_file, save_driver_kyc_document_file
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

ALLOWED_EXTENSIONS = [".pdf"]



def update_driver_kyc_documents(
    driver: Driver,
    files: list[UploadFile],
    document_types: list[KYCDocumentTypeEnum],
    db: Session,
) -> list[KYCDocumentSchema]:
    """
    For each file and document type:
    - If document type exists in kyc_documents, overwrite it and update file, because
    we only want the latest version of each document type. This also simplifies the logic since we don't have to manage multiple versions of the same document type.

    - If not, append new document entry.
    - Always save file as {doc_type}.{ext} in share/documents/drivers/{driver_id}/
    """
    try:
        kyc_docs = driver.kyc_documents or []

        kyc_docs_dict = (
            {
                doc["document_type"]: KYCDocumentSchema.model_validate(doc)
                for doc in kyc_docs
            }
            if kyc_docs
            else {}
        )

        qualified_for_update = False

        for file, doc_type in zip(files, document_types):
            if file.size is None or file.size == 0:
                print("Skipping empty file for document type:", doc_type)
                continue  # Skip empty files
            extension = os.path.splitext(file.filename)[-1].lower()
            if extension not in ALLOWED_EXTENSIONS:
                print("Unsupported file type for document type:", doc_type)
                continue  # Skip unsupported file types

            # Overwrite existing document of the same type or add new document entry
            # Here unlike profile pictures, we do not remove the existing document type entry as kyc documents are
            # actually names of files (instead of hex) and hence we keep on adding or overwriting the same document type entry with new file info. 
            # This way we can maintain the history of document uploads by looking at the file info (like upload timestamp) without having to manage multiple versions of the same document type in the database.
            s3_result = save_driver_kyc_document_file(
                driver.id, file, doc_type
            )
            if not s3_result:
                print("Failed to save file for document type:", doc_type)
                continue  # Skip if file saving failed
            doc_entry = KYCDocumentSchema(
                document_id=uuid4().hex,
                document_type=doc_type.value,
                document_info=s3_result,
                verified=False,  # We have separate endpoint to verify
                extension=extension,
                size=file.size if hasattr(file, "size") else None,
            )

            # Overwrite or add
            kyc_docs_dict[doc_type.value] = doc_entry.model_dump(
                exclude_none=True, exclude_unset=True
            )
            qualified_for_update = True

        # Update driver in DB
        if not qualified_for_update:
            return []

        driver.kyc_documents = list(kyc_docs_dict.values())
        db.commit()
        db.refresh(driver)
        # Convert back to list of KYCDocumentSchema
        response = [
            KYCDocumentSchema.model_validate(doc) for doc in driver.kyc_documents
        ]
        return response
    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error updating KYC documents: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def create_master_kyc_data(db: Session):
    kyc_document_types = [
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.aadhar_card,
            document_alias="Aadhar Card",
            document_description="Government-issued identity card with a unique 12-digit number.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.pan_card,
            document_alias="PAN Card",
            document_description="Permanent Account Number card issued by the Income Tax Department.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.driving_license,
            document_alias="Driving License",
            document_description="Official document permitting an individual to operate one or more motorized vehicles.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.vehicle_registration_certificate,
            document_alias="Vehicle Registration Certificate",
            document_description="Official document proving ownership and registration of a vehicle.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.vehicle_insurance,
            document_alias="Vehicle Insurance",
            document_description="Insurance policy document covering damages and liabilities related to a vehicle.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.pollution_certificate,
            document_alias="Pollution Certificate",
            document_description="Certificate proving that a vehicle meets pollution control standards.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.passport,
            document_alias="Passport",
            document_description="Official government document that certifies the holder's identity and citizenship.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.voter_id,
            document_alias="Voter ID",
            document_description="Identification card issued by the Election Commission of India to eligible voters.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.bank_statement,
            document_alias="Bank Statement",
            document_description="Official statement from a bank detailing account activity over a specified period.",
        ),
        KYCDocumentTypes(
            document_type=KYCDocumentTypeEnum.utility_bill,
            document_alias="Utility Bill",
            document_description="Recent bill from a utility provider (electricity, water, gas) showing the customer's name and address.",
        ),
    ]
    db.add_all(kyc_document_types)
    db.flush()


def remove_kyc_document_by_id_for_driver(
    driver: Driver,
    document_id: str,
    db: Session,
) -> tuple[bool, str | None]:
    """
    Remove KYC document by document_id for the given driver.
    """
    try:
        kyc_docs = driver.kyc_documents or []
        if len(kyc_docs) == 0:
            return False, "No KYC documents to remove"

        kyc_docs_dict = {
            doc["document_id"]: KYCDocumentSchema.model_validate(doc)
            for doc in kyc_docs
        }

        if document_id in kyc_docs_dict:
            s3_document_info = kyc_docs_dict[document_id].document_info or None
            # Delete the file from S3 storage
            if s3_document_info is not None:
                removed = remove_driver_kyc_document_file(s3_document_info.key)
                if not removed:
                    return False, "Failed to remove KYC document file from storage"

                # Remove from dict
                del kyc_docs_dict[document_id]
                driver.kyc_documents = [
                    doc.model_dump(exclude_none=True, exclude_unset=True)
                    for doc in kyc_docs_dict.values()
                ]

                db.commit()
                db.refresh(driver)
                return True, None
            return False, "No document info found for the specified document ID"
        else:
            return (
                False,
                "Document ID not found",
            )  # Document ID not found; nothing to remove

    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error removing KYC document: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


def list_kyc_documents(driver: Driver, db: Session) -> list[KYCDocumentSchema]:
    """
    Retrieve all KYC document types from the database.
    """
    return [KYCDocumentSchema.model_validate(doc) for doc in driver.kyc_documents]


def mark_kyc_verification_status_for_driver_document(
    driver: Driver,
    document_id: str,
    status: bool,
    db: Session,
) -> KYCDocumentSchema:
    """
    Mark a specific KYC document as verified for the given driver.
    Also updates driver's overall kyc_verified status.
    If any document is unverified, driver's kyc_verified is set to False.
    If all documents are verified, driver's kyc_verified is set to True.
    """
    try:
        kyc_docs = driver.kyc_documents or []
        if len(kyc_docs) == 0:
            raise CabboException(
                "No KYC documents found for this driver.", status_code=404
            )

        kyc_docs_dict = {
            doc["document_id"]: KYCDocumentSchema.model_validate(doc)
            for doc in kyc_docs
        }

        if document_id in kyc_docs_dict:
            kyc_doc = kyc_docs_dict[document_id]
            kyc_doc.verified = status

            # Update the document in the dict
            kyc_docs_dict[document_id] = kyc_doc

            # Update driver's kyc_documents
            driver.kyc_documents = [
                doc.model_dump(exclude_none=True, exclude_unset=True)
                for doc in kyc_docs_dict.values()
            ]
            if status == False:
                # If any document is unverified, set driver's kyc_verified to False
                driver.kyc_verified = False
            elif all(doc.verified for doc in kyc_docs_dict.values()):
                driver.kyc_verified = True  # All documents verified

            db.commit()
            db.refresh(driver)

            return kyc_doc
        else:
            raise CabboException("KYC document not found.", status_code=404)

    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error marking KYC document as verified: {str(e)}",
            status_code=500,
            include_traceback=True,
        )


async def async_add_kyc_document_record(
    payload: KYCDocumentSchema, db: AsyncSession, created_by: str = RoleEnum.system.value
):
    """
    Async function to add a KYC document record to the database.
    """
    new_record = KYCDocumentTypes(
        document_type=payload.document_type,
        document_alias=payload.document_alias,
        document_description=payload.document_description,
        created_by=created_by,
    )
    try:
        db.add(new_record)
        await db.commit()
        await db.refresh(new_record)
        return KYCDocumentTypeSchema.model_validate(new_record), None
    except Exception as e:
        await db.rollback()
        print(f"Error adding KYC document record: {e}")
        return None, str(e)

async def async_get_all_kyc_document_records(db: AsyncSession) -> list[KYCDocumentTypeSchema]:
    """Async function to retrieve all KYC document records from the database."""
    result = await db.execute(select(KYCDocumentTypes))
    records = result.scalars().all()
    return [KYCDocumentTypeSchema.model_validate(record) for record in records]

async def async_get_kyc_document_record_by_id(document_id: str, db: AsyncSession) -> KYCDocumentTypeSchema | None:
    """Async function to retrieve a KYC document record by its ID."""
    result = await db.execute(select(KYCDocumentTypes).where(KYCDocumentTypes.id == document_id))
    record = result.scalar_one_or_none()
    if record:
        return KYCDocumentTypeSchema.model_validate(record)
    return None

async def async_delete_kyc_document_record(document_id: str, db: AsyncSession) -> tuple[bool, str | None]:
    """Async function to delete a KYC document record from the database."""
    try:
        result = await db.execute(select(KYCDocumentTypes).where(KYCDocumentTypes.id == document_id))
        record = result.scalar_one_or_none()
        if record is None:
            return False, f"KYC document record with id {document_id} not found."
        if record.is_active == False:
            return False, "KYC document record is already inactive."
        record.is_active=False  # Soft delete by marking as inactive
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        print(f"Error deleting KYC document record: {e}")
        return False, str(e)


async def async_update_kyc_document_record(document_id: str, payload: KYCDocumentUpdateSchema, db: AsyncSession) -> tuple[KYCDocumentTypeSchema | None, str | None]:
    """Async function to update an existing KYC document record in the database."""
    try:
        result = await db.execute(select(KYCDocumentTypes).where(KYCDocumentTypes.id == document_id))
        record = result.scalar_one_or_none()
        if record is None:
            return None, f"KYC document record with id {document_id} not found."
        if payload.document_alias is not None:
            record.document_alias = payload.document_alias
        if payload.document_description is not None:
            record.document_description = payload.document_description
        await db.commit()
        await db.refresh(record)
        return KYCDocumentTypeSchema.model_validate(record), None
    except Exception as e:
        await db.rollback()
        print(f"Error updating KYC document record: {e}")
        return None, str(e)
    
async def async_activate_kyc_document_record(document_id:str, db:AsyncSession) -> tuple[bool, str | None]:
    """Async function to activate a KYC document record in the database."""
    try:
        result = await db.execute(select(KYCDocumentTypes).where(KYCDocumentTypes.id == document_id))
        record = result.scalar_one_or_none()
        if record is None:
            return False, f"KYC document record with id {document_id} not found."
        if record.is_active == True:
            return False, "KYC document record is already active."
        record.is_active=True  # Activate the document type
        await db.commit()
        return True, None
    except Exception as e:
        await db.rollback()
        print(f"Error activating KYC document record: {e}")
        return False, str(e)