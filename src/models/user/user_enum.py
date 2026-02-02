from enum import Enum


class GenderEnum(str, Enum):
    male = "male"
    female = "female"
    transgender = "transgender"
    prefer_not_to_disclose = "prefer_not_to_disclose"

class NationalityEnum(str, Enum):
    indian = "Indian"
    american = "American"
    british = "British"
    australian = "Australian"
    canadian = "Canadian"
    other = "Other"

class ReligionEnum(str, Enum):
    hindu = "Hindu"
    muslim = "Muslim"
    christian = "Christian"
    sikh = "Sikh"
    buddhist = "Buddhist"
    jain = "Jain"
    other = "Other"
    prefer_not_to_disclose = "Prefer not to disclose"