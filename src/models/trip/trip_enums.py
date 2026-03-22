import enum


# Trip-related Enums


# Happy Path transition flow for trip status:
# created -> confirmed(driver_admin) -> ongoing -> completed

# Worst Case transition flow for trip status:
# created -> confirmed(driver_admin) -> cancelled(by customer)
# created -> confirmed(driver_admin) -> cancelled due to customer_no_show(by super admin or driver_admin)
# created -> confirmed(driver_admin) -> cancelled due to driver_unavailable,driver_cancelled, driver_no_show, other(by super admin or driver_admin)

# created -> confirmed(driver_admin) -> ongoing -> completed -> dispute(reported by driver and/or customer and updated by super admin or driver admin after investigation) 
 


# Trip Status Enum stores the various states a trip can be in during its lifecycle.
# We do not need to store the status in the database, as it is derived from the trip status audit logs.
class TripStatusEnum(str, enum.Enum):
    created = "created"
    pending= "pending"  # Trip is created but not yet confirmed or assigned
    confirmed = "confirmed"
    ongoing = "ongoing" #alias to started, trip is currently in progress
    completed = "completed"  # Trip completed successfully
    cancelled = "cancelled" # Trip cancelled by customer or admin due to various reasons
    dispute = "dispute" # Customer fled without paying on completion of trip


# Cancellation Sub-status Enum stores the various sub-states a cancellation can have.
# This is useful for understanding the reason for cancellation and taking appropriate actions.
class CancellationSubStatusEnum(str, enum.Enum):
    none = "none"
    customer_cancelled = "customer_cancelled"
    customer_no_show = "customer_no_show"
    driver_cancelled = "driver_cancelled"
    driver_unavailable = "driver_unavailable"
    driver_no_show = "driver_no_show"
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
