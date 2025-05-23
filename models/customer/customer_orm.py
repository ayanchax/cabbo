from sqlalchemy import Column, String, DateTime, func, Integer, Boolean, Text, ForeignKey
from sqlalchemy.dialects.mysql import CHAR
from db.database import Base
import uuid

class Customer(Base):
    __tablename__ = "customers"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.utc_timestamp())
    is_phone_verified = Column(Boolean, default=False, nullable=False)
    is_email_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    last_modified = Column(DateTime, default=func.utc_timestamp(), nullable=True)
    bearer_token = Column(Text, nullable=True)
    last_seen = Column(DateTime, nullable=True)
    
class PreOnboardingCustomer(Base): 
    __tablename__ = "pre_onboarding_customers"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    otp_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, server_default=func.utc_timestamp(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_sent_at = Column(DateTime, server_default=func.utc_timestamp(), nullable=False)

class CustomerEmailVerification(Base):
    __tablename__ = "customer_email_verification"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(CHAR(36), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False, index=True)
    verification_url = Column(String(512), nullable=False, unique=True)
    expiry = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.utc_timestamp(), nullable=False)

