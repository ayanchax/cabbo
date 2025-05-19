import random
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from models.customer.customer_orm import PreOnboardingCustomer

OTP_LENGTH = 4
OTP_EXPIRY_MINUTES = 5
OTP_RESEND_INTERVAL_SECONDS = 60
MAX_ATTEMPTS = 3

# Helper to generate a unique 4-digit OTP based on phone number and current time
# Ensures no repeat for the same phone number

def generate_otp(phone_number: str, db: Session) -> str:
    now = datetime.now(timezone.utc)
    # Check for existing, non-expired OTP for this phone number and attempts not exceeded
    existing = db.query(PreOnboardingCustomer).filter(
        PreOnboardingCustomer.phone_number == phone_number,
        PreOnboardingCustomer.expires_at > now,
        PreOnboardingCustomer.attempts < MAX_ATTEMPTS
    ).first()
    if existing:
        raise Exception(f"OTP already sent and not expired, or max attempts not reached. Please wait for {OTP_EXPIRY_MINUTES} minutes before requesting a new otp or use the existing OTP.")
    # Remove any expired OTPs for this phone number
    db.query(PreOnboardingCustomer).filter(
        PreOnboardingCustomer.phone_number == phone_number,
        PreOnboardingCustomer.expires_at < now
    ).delete()
    db.commit()
    # Generate a unique, cryptographically secure 4-digit OTP not in use
    for _ in range(10):  # Try up to 10 times to avoid rare infinite loop
        otp_int = secrets.randbelow(10000)
        otp = f"{otp_int:04d}"
        if not db.query(PreOnboardingCustomer).filter(PreOnboardingCustomer.otp_hash == hash_otp(otp)).first():
            #no collision found, break
            break
    else:
        raise Exception("Unable to generate unique OTP after several attempts")
    # Store OTP (hashed) in DB
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    last_sent_at = now
    otp_hash_val = hash_otp(otp)
    pre = PreOnboardingCustomer(
        phone_number=phone_number,
        otp_hash=otp_hash_val,
        created_at=now,
        expires_at=expires_at,
        attempts=0,
        last_sent_at=last_sent_at
    )
    db.add(pre)
    db.commit()
    return otp

def hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()

def verify_otp(phone_number: str, otp: str, db: Session) -> bool:
    now = datetime.now(timezone.utc)
    otp_hash_val = hash_otp(otp)
    record = db.query(PreOnboardingCustomer).filter(
        PreOnboardingCustomer.phone_number == phone_number,
    ).first()
    if not record:
        return False
    if record.expires_at < now:
        delete_otp(phone_number, db)
        return False
    if record.otp_hash != otp_hash_val:
        increment_attempt(phone_number, db)
        return False
    # Success: delete OTP row
    delete_otp(phone_number, db)
    return True

def can_resend_otp(phone_number: str, db: Session) -> bool:
    now = datetime.now(timezone.utc)
    record = db.query(PreOnboardingCustomer).filter(
        PreOnboardingCustomer.phone_number == phone_number
    ).first()
    if not record:
        return True
    return (now - record.last_sent_at).total_seconds() > OTP_RESEND_INTERVAL_SECONDS

def increment_attempt(phone_number: str, db: Session):
    record = db.query(PreOnboardingCustomer).filter(
        PreOnboardingCustomer.phone_number == phone_number
    ).first()
    if record:
        record.attempts = record.attempts + 1
        db.commit()
        if record.attempts >= MAX_ATTEMPTS:
            delete_otp(phone_number, db)

def delete_otp(phone_number: str, db: Session):
    db.query(PreOnboardingCustomer).filter(
        PreOnboardingCustomer.phone_number == phone_number
    ).delete()
    db.commit()
