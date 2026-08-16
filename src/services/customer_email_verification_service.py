from datetime import datetime, timezone
import logging
from sqlalchemy import select
from db.database import AsyncSessionLocal
from  models.customer.customer_orm import CustomerEmailVerification
from services.message_service import create_email_verification_link
from sqlalchemy.ext.asyncio import AsyncSession


log = logging.getLogger(__name__)
EMAIL_VERIFY_EXPIRY_UNIT=2
EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME={
    "DAYS": "days",
    "HOURS": "hours",
    "MINUTES": "minutes",
}

 


async def a_get_existing_email_verification_link(
    customer_id: str, db: AsyncSession
):
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(CustomerEmailVerification).where(
            CustomerEmailVerification.customer_id == customer_id,
            CustomerEmailVerification.expiry > now
        )
    )
    existing = result.scalar_one_or_none()

    return existing

 
async def a_is_email_verification_link_valid(
    customer_id: str, token: str, db: AsyncSession
):
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(CustomerEmailVerification).where(
            CustomerEmailVerification.customer_id == customer_id,
            CustomerEmailVerification.verification_url.like(f"%{token}"),
            CustomerEmailVerification.expiry > now
        )
    )
    record = result.scalar_one_or_none()

    return record if record else False

 
async def a_remove_email_verification(email_verification:CustomerEmailVerification, db:AsyncSession):
    try:
            await db.delete(email_verification)
            await db.commit()
            return True
    except Exception as e:
        log.error(f"remove_email_verification: unexpected error for email_verification {email_verification.id}: {e}")
        await db.rollback()
        return False    
    
 

async def a_create_customer_email_verification(customer_id:str, db:AsyncSession):
    try:
        verification_url, expiry = create_email_verification_link(id=customer_id, endpoint=f"/customer/email-verification/verify")
        email_verification = CustomerEmailVerification(
            customer_id=customer_id,
            verification_url=verification_url,
            expiry=expiry
        )
        db.add(email_verification)
        await db.commit()
        await db.refresh(email_verification)
        return email_verification
    except Exception as e:
        await db.rollback()
        log.error(f"create_customer_email_verification: unexpected error for customer {customer_id}: {e}")
        return None



async def send_email_verification(customer_id: str) -> None:
    """
    Background task to initiate email verification for a customer.
    Manages its own DB session. Safe to run as a background task — failures are logged and swallowed.
    """
    from services.customer_service import (
        a_get_active_customer_by_id,
        a_is_customer_email_verified,
    )
    from services.notification_service import notify_verification_email_to_customer
    from models.customer.customer_schema import CustomerRead
    async with AsyncSessionLocal() as db:
        try:
            if await a_is_customer_email_verified(customer_id, db):
                return
            customer = await a_get_active_customer_by_id(customer_id, db)
            if not customer or not customer.email:
                return
            existing = await a_get_existing_email_verification_link(customer_id, db)
            if existing:
                verification_link = existing.verification_url
            else:
                record = await a_create_customer_email_verification(customer_id, db)
                if not record:
                    log.error(f"send_email_verification: failed to create verification record for customer {customer_id}")
                    return
                verification_link = record.verification_url
            await notify_verification_email_to_customer(
                customer=CustomerRead.model_validate(customer),
                verification_url=verification_link,
            )
        except Exception as e:
            log.error(f"send_email_verification: unexpected error for customer {customer_id}: {e}")
