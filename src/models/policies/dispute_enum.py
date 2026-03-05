

from enum import Enum


class DisputeTypeEnum(str, Enum):
    fare = "fare"
    service = "service"
    other = "other"
    unknown = "unknown"