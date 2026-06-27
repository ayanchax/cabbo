from fastapi import APIRouter, Depends
from core.config import settings
from core.security import validate_customer_token
from db.database import a_yield_mysql_session
from models.customer.customer_orm import Customer
from models.support.support_enum import SupportTypeEnum
from models.support.support_schema import (
    CustomerSupportContactLookupRequest,
    CustomerSupportContactSchema,
)
from services.support_service import get_best_support_contact, get_support_geography_ids
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.post(
    "/",
    response_model=CustomerSupportContactSchema,
)
async def get_support_contact_for_trip(
    payload: CustomerSupportContactLookupRequest,
    db: AsyncSession = Depends(a_yield_mysql_session),
    _: Customer = Depends(validate_customer_token),
):
    region_id, state_id, country_id = await get_support_geography_ids(
        trip_type=payload.trip_type,
        origin=payload.origin,
        db=db,
    )

    support_contact = await get_best_support_contact(
        db=db,
        support_type=SupportTypeEnum.customer,
        trip_type_scope=payload.trip_type.value,
        region_id=region_id,
        state_id=state_id,
        country_id=country_id,
    )

    if support_contact:
        return CustomerSupportContactSchema.model_validate(support_contact)

    # Default support contact if no specific support contact is found for the trip's geography and trip type
    return CustomerSupportContactSchema(
        display_name="Cabbo Customer Support",
        email=settings.CUSTOMER_SUPPORT_EMAIL,
        phone_number=settings.CUSTOMER_SUPPORT_PHONE_NUMBER,
        whatsapp_number=settings.CUSTOMER_SUPPORT_WHATSAPP_NUMBER,
        support_type=SupportTypeEnum.customer,
    )
