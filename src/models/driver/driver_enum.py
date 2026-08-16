
import enum


class DriverAssignmentFitLevelEnum(str, enum.Enum):
    no_criteria = "no_criteria"
    best_fit = "best_fit"
    good_fit = "good_fit"
    review_fit = "review_fit"


class DriverAssignmentFitSignalEnum(str, enum.Enum):
    good_fit = "good_fit"
    cab_type_mismatch = "cab_type_mismatch"
    fuel_type_mismatch = "fuel_type_mismatch"
    capacity_mismatch = "capacity_mismatch"
