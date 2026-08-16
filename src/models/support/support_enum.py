from enum import Enum


class TicketStatusEnum(str, Enum):
    open = "open"
    in_progress = "in_progress"
    resolved = "resolved"
    closed = "closed"

class TicketPriorityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"

class SupportTypeEnum(str, Enum):
    customer = "customer"
    driver = "driver"
    booking = "booking"
    payment = "payment"
    emergency = "emergency"
    general = "general"


class SupportScopeEnum(str, Enum):
    country = "country"
    state = "state"
    region = "region"


