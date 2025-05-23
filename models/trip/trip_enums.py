import enum


class TripStatusEnum(str, enum.Enum):
    created = "created"
    quoted = "quoted"
    accepted = "accepted"
    confirmed = "confirmed"
    assigned = "assigned"
    ongoing = "ongoing"
    completed = "completed"
    cancelled = "cancelled"


class TripTypeEnum(str, enum.Enum):
    local = "local"
    outstation = "outstation"


# Add other trip-related enums/constants here as needed
