import enum


# Trip-related Enums


# Trip Status Enum stores the various states a trip can be in during its lifecycle.
# We do not need to store the status in the database, as it is derived from the trip status audit logs.
class TripStatusEnum(str, enum.Enum):
    created = "created"
    quoted = "quoted"
    pending_admin_review = "pending_admin_review"
    quote_accepted = "quote_accepted"
    confirmed = "confirmed"
    assigned = "assigned"  # Driver assigned to the trip
    ongoing = "ongoing"
    completed = "completed"  # Trip completed successfully
    closed = "closed"  # Trip closed after completion with all dues settled
    no_show = "no_show"  # Customer did not show up for the trip
    cancelled = "cancelled"
    dispute = "dispute"


# Cancellation Sub-status Enum stores the various sub-states a cancellation can have.
# This is useful for understanding the reason for cancellation and taking appropriate actions.
class CancellationSubStatusEnum(str, enum.Enum):
    none = "none"
    customer_cancelled = "customer_cancelled"
    system_cancelled = "system_cancelled"
    sys_admin_cancelled = "sys_admin_cancelled"
    driver_admin_cancelled = "driver_admin_cancelled"
    finance_admin_cancelled = "finance_admin_cancelled"
    driver_cancelled = "driver_cancelled"
    driver_unavailable = "driver_unavailable"
    driver_no_show = "driver_no_show"
    customer_no_show = "customer_no_show"
    payment_failed = "payment_failed"
    technical_issue = "technical_issue"
    customer_preferences_not_met = (
        "customer_preferences_not_met"  # e.g., car type, fuel type, etc.
    )
    other = "other"


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
