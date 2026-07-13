import enum


class KYCDocumentTypeEnum(str, enum.Enum):
    aadhar_card = "aadhaar_card"
    pan_card = "pan_card"
    driving_license = "driver_license"
    passport = "passport"
    voter_id = "voter_id"
    vehicle_registration_certificate = "vehicle_registration"
    vehicle_insurance = "insurance"
    pollution_certificate = "pollution_certificate"
    bank_statement = "bank_statement"
    utility_bill = "utility_bill"

    