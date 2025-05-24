import enum


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


class TripTypeEnum(str, enum.Enum):
    local = "local"
    outstation = "outstation"
    airport_pickup = "airport_pickup"
    airport_drop = "airport_drop"


class FuelTypeEnum(str, enum.Enum):
    diesel = "diesel"
    petrol = "petrol"
    cng = "cng"


class CarTypeEnum(str, enum.Enum):
    hatchback = "Hatchback"
    sedan = "Sedan"
    suv = "SUV"
    suv_plus = "SUV+"


# Add other trip-related enums/constants here as needed
