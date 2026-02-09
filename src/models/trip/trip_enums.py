import enum


# Trip-related Enums


# Happy Path transition flow for trip status:
# created -> confirmed(driver_admin) -> assigned -> ongoing -> completed -> closed

# Worst Case transition flow for trip status:
# created -> cancelled(by admin)
# created -> cancelled(by customer)
# created -> confirmed -> no_show(by customer)
# created -> confirmed -> assigned -> ongoing -> completed -> dispute(by customer)
 


# Trip Status Enum stores the various states a trip can be in during its lifecycle.
# We do not need to store the status in the database, as it is derived from the trip status audit logs.
class TripStatusEnum(str, enum.Enum):
    created = "created"
    pending= "pending"  # Trip is created but not yet confirmed or assigned
    confirmed = "confirmed"
    assigned = "assigned"  # Driver assigned to the trip
    ongoing = "ongoing"
    completed = "completed"  # Trip completed successfully
    closed = "closed"  # Trip closed after completion with all dues settled between cabbo, customer and driver
    cancelled = "cancelled" # Trip cancelled by customer or admin due to various reasons
    dispute = "dispute" # Customer fled without paying on completion of trip


# Cancellation Sub-status Enum stores the various sub-states a cancellation can have.
# This is useful for understanding the reason for cancellation and taking appropriate actions.
class CancellationSubStatusEnum(str, enum.Enum):
    none = "none"
    customer_cancelled = "customer_cancelled"
    customer_no_show = "customer_no_show"
    super_admin_cancelled = "super_admin_cancelled"
    driver_admin_cancelled = "driver_admin_cancelled"
    driver_cancelled = "driver_cancelled"
    driver_unavailable = "driver_unavailable"
    driver_no_show = "driver_no_show"
    finance_admin_cancelled = "finance_admin_cancelled"
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
