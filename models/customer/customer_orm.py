from sqlalchemy import Column, String, DateTime, func, Integer
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

class PreOnboardingCustomer(Base):
    __tablename__ = "pre_onboarding_customers"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    otp_hash = Column(String(128), nullable=False)
    created_at = Column(DateTime, server_default=func.utc_timestamp(), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_sent_at = Column(DateTime, server_default=func.utc_timestamp(), nullable=False)
 
