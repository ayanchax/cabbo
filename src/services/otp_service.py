from enum import Enum
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy import delete, select
from core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from core.security import generate_simple_hash
from models.customer.customer_orm import PreOnboardingCustomer
from core.exceptions import OTP_ALREADY_SENT, OTP_GENERATION_FAILED, OTP_RESEND_TOO_SOON, CabboException
OTP_LENGTH = settings.OTP_LENGTH
OTP_EXPIRY_MINUTES = settings.OTP_EXPIRY_MINUTES
OTP_RESEND_INTERVAL_SECONDS = settings.OTP_RESEND_COOLDOWN_SECONDS # Minimum time between OTP sends to prevent abuse
MAX_ATTEMPTS = settings.OTP_VERIFICATION_MAX_ATTEMPTS # Maximum attempts allowed for OTP verification before invalidating the OTP 

class OTPFlow(str, Enum):
    REGISTRATION="registration"
    LOGIN="login"
    RESEND="resend"
# Helper to generate a unique 6-digit OTP based on phone number and current time
# Ensures no repeat for the same phone number

async def a_generate_otp(phone_number: str, db: AsyncSession) -> tuple[str, datetime, int, datetime]:
    now = datetime.now(timezone.utc)
    # Check for existing, non-expired OTP for this phone number and attempts not exceeded
    result = await db.execute(
        select(PreOnboardingCustomer).filter(
            PreOnboardingCustomer.phone_number == phone_number,
            PreOnboardingCustomer.expires_at > now,
            PreOnboardingCustomer.attempts < MAX_ATTEMPTS
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        raise CabboException(f"OTP already sent and not expired, or max attempts not reached. Please wait for {OTP_EXPIRY_MINUTES} minutes before requesting a new otp or use the existing OTP.", status_code=400, include_traceback=True, error_code=OTP_ALREADY_SENT)

    # Remove any expired OTPs for this phone number
    await a_delete_expired_otp(phone_number, db)
    # In case otp is not expired, but attempts got exhausted, then the above delete_expired_otp would do nothing technically - but still we would generate new otp without complaining about invalid otp attempts - because we care for onboarding/login the customer seamlessly and without irrelevant security errors.
    # We will anyway have a OTP clean up job from PreOnboardingCustomer table to clear any expired OTPs, that will run once everyday.
    # Generate a unique, cryptographically secure 6-digit OTP not in use
    for _ in range(10):  # Try up to 10 times to avoid rare infinite loop
        otp_int = secrets.randbelow(10 ** OTP_LENGTH)  # Generate a random integer with OTP_LENGTH digits
        otp = f"{otp_int:0{OTP_LENGTH}d}"
        result = await db.execute(
            select(PreOnboardingCustomer).filter(
                PreOnboardingCustomer.otp_hash == generate_simple_hash(otp)
            )
        )
        if not result.scalar_one_or_none():
            #no collision found, break
            break
    else:
         raise CabboException("Unable to generate unique OTP after several attempts", status_code=500, include_traceback=True, error_code=OTP_GENERATION_FAILED)
    

    record = await a_store_otp(phone_number, otp, db)
    return otp, record.expires_at, record.attempts, record.last_sent_at

 
async def a_store_otp(phone_number: str, otp: str, db: AsyncSession):
    try:
        # Store OTP (hashed) in DB
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
        last_sent_at = now
        otp_hash_val = generate_simple_hash(otp)
        pre = PreOnboardingCustomer(
            phone_number=phone_number,
            otp_hash=otp_hash_val,
            created_at=now,
            expires_at=expires_at,
            attempts=0,
            last_sent_at=last_sent_at
        )
        db.add(pre)
        await db.commit()
        await db.refresh(pre)
        return pre
    except Exception as e:
        await db.rollback()
        raise e


 

async def a_verify_otp(phone_number: str, otp: str, db: AsyncSession) -> tuple[bool, str]:
    now = datetime.now(timezone.utc)
    otp_hash_val = generate_simple_hash(otp)
    result = await db.execute(
        select(PreOnboardingCustomer).filter(
            PreOnboardingCustomer.phone_number == phone_number
        )
    )
    record = result.scalar_one_or_none()
    if not record:
        return False, "No OTP found for this phone number. Please request a new OTP."
    # Ensure both datetimes are timezone-aware for comparison
    record_expiry = record.expires_at
    if record_expiry.tzinfo is None:
        record_expiry = record_expiry.replace(tzinfo=timezone.utc)
    if record_expiry < now:
        await a_delete_otp(phone_number, db)
        return False, "OTP has expired. Please request a new OTP."
    if record.otp_hash != otp_hash_val:
        await a_increment_attempt(phone_number, db)
        return False, "Invalid OTP. Please try again."
    # Success: delete OTP row
    await a_delete_otp(phone_number, db)
    return True, "OTP verified successfully."


 
async def a_can_resend_otp(phone_number: str, db: AsyncSession) -> bool:
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(PreOnboardingCustomer).where(
            PreOnboardingCustomer.phone_number == phone_number
        )
    )
    record = result.scalar_one_or_none()

    if not record:
        return True

    last_sent_at = record.last_sent_at
    if last_sent_at.tzinfo is None:
        last_sent_at = last_sent_at.replace(tzinfo=timezone.utc)

    return (now - last_sent_at).total_seconds() > OTP_RESEND_INTERVAL_SECONDS

async def a_increment_attempt(phone_number: str, db: AsyncSession):
    try:
        record = await db.execute(
            select(PreOnboardingCustomer).filter(
                PreOnboardingCustomer.phone_number == phone_number
            )
        )
        record = record.scalar_one_or_none()
        if record:
            record.attempts = record.attempts + 1
            await db.commit()
            if record.attempts >= MAX_ATTEMPTS:
                await a_delete_otp(phone_number, db)
    except Exception as e:
        await db.rollback()
        raise e

 
async def a_delete_otp(phone_number: str, db: AsyncSession):
    try:
        record = await db.execute(
            select(PreOnboardingCustomer).filter(
                PreOnboardingCustomer.phone_number == phone_number
            )
        )
        record = record.scalar_one_or_none()
        if record:
            await db.delete(record)
            await db.commit()
    except Exception as e:
        await db.rollback()
        raise e

 
async def a_delete_expired_otp(phone_number: str, db: AsyncSession):

    try:
        now = datetime.now(timezone.utc)
        await db.execute(
            delete(PreOnboardingCustomer).where(
                PreOnboardingCustomer.phone_number == phone_number,
                PreOnboardingCustomer.expires_at < now
            )
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise e
    

async def a_resend_otp(phone_number: str, db: AsyncSession) -> tuple[str, datetime, int, datetime]:
    if not await a_can_resend_otp(phone_number, db):
        raise CabboException(f"OTP was sent recently. Please wait before requesting a new OTP.", status_code=400,error_code=OTP_RESEND_TOO_SOON, include_traceback=True)
    await a_delete_otp(phone_number, db) # Delete existing OTP (if any) before generating a new one to ensure only one valid OTP exists at a time
    return await a_generate_otp(phone_number, db)
