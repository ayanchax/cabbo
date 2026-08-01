import enum


class KYCDocumentTypeEnum(str, enum.Enum):
    aadhar_card = "aadhaar_card" # mandatory verification
    pan_card = "pan_card" 
    driving_license = "driver_license" # mandatory verification
    passport = "passport"
    voter_id = "voter_id"
    vehicle_registration_certificate = "vehicle_registration" # mandatory verification
    vehicle_insurance = "insurance"
    pollution_certificate = "pollution_certificate"
    fitness_certificate = "fitness_certificate" 
    bank_statement = "bank_statement"
    utility_bill = "utility_bill"

    