from datetime import datetime, timezone
from sqlalchemy.orm import Session
from  models.customer.customer_orm import CustomerEmailVerification
from services.message_service import create_email_verification_link
EMAIL_VERIFY_EXPIRY_UNIT=2
EMAIL_VERIFY_EXPIRY_UNIT_TIME_FRAME={
    "DAYS": "days",
    "HOURS": "hours",
    "MINUTES": "minutes",
}

def is_email_verification_link_already_sent(customer_id:str, db:Session):
    now = datetime.now(timezone.utc)
    existing = db.query(CustomerEmailVerification).filter(
        CustomerEmailVerification.customer_id == customer_id,
        CustomerEmailVerification.expiry > now
    ).first()
    return existing is not None

def is_email_verification_link_valid(customer_id:str, token:str, db:Session):
    
    now = datetime.now(timezone.utc)
    record = db.query(CustomerEmailVerification).filter(
        CustomerEmailVerification.customer_id == customer_id,
        CustomerEmailVerification.verification_url.like(f"%{token}"),
        CustomerEmailVerification.expiry > now
    ).first()
    return record if record else False

def remove_email_verification(email_verification:CustomerEmailVerification, db:Session):
    try:
            db.delete(email_verification)
            db.commit()
            return True
    except Exception as e:
        db.rollback()
        return False    
    
def create_customer_email_verification(customer_id:str, db:Session):
    try:
        verification_url, expiry = create_email_verification_link(id=customer_id, endpoint=f"/customer/email-verification/verify")
        email_verification = CustomerEmailVerification(
            customer_id=customer_id,
            verification_url=verification_url,
            expiry=expiry
        )
        db.add(email_verification)
        db.commit()
        db.refresh(email_verification)
        return email_verification
    except Exception as e:
        db.rollback()
        return None