from models.documents.kyc_document_enum import KYCDocumentTypeEnum
from models.documents.kyc_document_orm import KYCDocumentTypes
from sqlalchemy.orm import Session

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