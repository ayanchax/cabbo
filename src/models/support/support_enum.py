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

