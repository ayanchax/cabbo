from uuid import uuid4
from core.exceptions import CabboException
from models.documents.kyc_document_enum import KYCDocumentTypeEnum
from models.documents.kyc_document_orm import KYCDocumentTypes
from sqlalchemy.orm import Session
import os
from fastapi import UploadFile
from core.config import settings
from models.documents.kyc_document_schema import KYCDocumentSchema
from models.driver.driver_orm import Driver
from services.file_service import create_directory

ALLOWED_EXTENSIONS = [".pdf"]


def _save_driver_kyc_document_file(
    driver_id: str, file: UploadFile, doc_type: KYCDocumentTypeEnum
) -> str:
    """
    Save the uploaded KYC document file to the driver's folder, renaming it according to the document type.
    Returns the relative file path.
    """
    folder = os.path.join(settings.SHARE_PATH, "documents", "drivers", driver_id)
    create_directory(folder)
    ext = os.path.splitext(file.filename)[-1]
    filename = f"{doc_type.value.lower()}{ext}"
    file_path = os.path.join(folder, filename)
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    return file_path, ext, file.size if hasattr(file, "size") else None


def update_driver_kyc_documents(
    driver: Driver,
    files: list[UploadFile],
    document_types: list[KYCDocumentTypeEnum],
    db: Session,
) -> list[KYCDocumentSchema]:
    """
    For each file and document type:
    - If document type exists in kyc_documents, overwrite it and update file.
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

            file_path, ext, size = _save_driver_kyc_document_file(
                driver.id, file, doc_type
            )
            doc_entry = KYCDocumentSchema(
                document_id=uuid4().hex,
                document_type=doc_type.value,
                document_url=file_path,
                verified=False,  # We have separate endpoint to verify
                extension=ext,
                size=size,
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
    db.commit()


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
            return False , "No KYC documents to remove"

        kyc_docs_dict = {
            doc["document_id"]: KYCDocumentSchema.model_validate(doc)
            for doc in kyc_docs
        }

        if document_id in kyc_docs_dict:
            url = kyc_docs_dict[document_id].document_url or None
            # Delete the file from storage
            if url and os.path.exists(url):
                os.remove(url)
            # Remove from dict
            del kyc_docs_dict[document_id]
            driver.kyc_documents = [
                doc.model_dump(exclude_none=True, exclude_unset=True)
                for doc in kyc_docs_dict.values()
            ]

            db.commit()
            db.refresh(driver)
            return True, None
        else:
            return False, "Document ID not found"  # Document ID not found; nothing to remove

    except Exception as e:
        db.rollback()
        raise CabboException(
            f"Error removing KYC document: {str(e)}",
            status_code=500,
            include_traceback=True,
        )

def list_kyc_documents(driver:Driver, db: Session) -> list[KYCDocumentSchema]:
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
    """
    try:
        kyc_docs = driver.kyc_documents or []
        if len(kyc_docs) == 0:
            raise CabboException("No KYC documents found for this driver.", status_code=404)

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
                driver.kyc_verified = True # All documents verified

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