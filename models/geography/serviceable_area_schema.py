from pydantic import BaseModel, Field


class ServiceableAreaSchema(BaseModel):
    country_code: str = Field(
        ..., description="ISO country code the region belongs to, e.g., 'IN' for India"
    )  # e.g. IN
    state_code: str = Field(
        ...,
        description="ISO state code the region belongs to, e.g., 'KA' for Karnataka",
    )  # e.g. KA
    region_code: str = Field(
        ..., description="Region code, e.g., 'BLR' for Bangalore"
    )  # e.g. BLR, MAA

    class Config:
        from_attributes = True
