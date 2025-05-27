import enum


# Trip-related Enums


# Trip Status Enum stores the various states a trip can be in during its lifecycle.
# We do not need to store the status in the database, as it is derived from the trip status audit logs.
class TripStatusEnum(str, enum.Enum):
    created = "created"
    quoted = "quoted"
    pending_admin_review = "pending_admin_review"
    accepted = "accepted"
    confirmed = "confirmed"
    assigned = "assigned"
    ongoing = "ongoing"
    completed = "completed"
    closed = "closed"
    cancelled = "cancelled"
    cancelled_by_customer = "cancelled_by_customer"
    cancelled_by_admin = "cancelled_by_admin"
    cancelled_no_driver = "cancelled_no_driver"
    dispute = "dispute"


# Trip Type Enum defines the type of trip being requested.
# Stored in the database as a string as these are admin editable, but can be extended with more types in the future.
class TripTypeEnum(str, enum.Enum):
    local = "local"
    outstation = "outstation"
    airport_pickup = "airport_pickup"
    airport_drop = "airport_drop"
    airport_general = "airport"  # common airport trip type for both pickup and drop


# Fuel Type Enum defines the type of fuel used by the vehicle.
# Stored in the database as a string as these are admin editable, but can be extended with more types in the future.
class FuelTypeEnum(str, enum.Enum):
    diesel = "diesel"
    petrol = "petrol"
    cng = "cng"


# Car Type Enum defines the type of car preferred for the trip.
# Stored in the database as a string as these are admin editable, but can be extended with more types in the future.
class CarTypeEnum(str, enum.Enum):
    hatchback = "Hatchback"  # mini
    sedan = "Sedan"
    sedan_plus = "Premium Sedan"
    suv = "SUV"
    suv_plus = "SUV+"
