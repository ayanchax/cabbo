from sqlalchemy import Column, Integer, String, DateTime, func
from sqlalchemy.dialects.mysql import CHAR
from db.database import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(CHAR(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    phone_number = Column(String(20), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
