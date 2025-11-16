#State or Province ORM model
from sqlalchemy import Column, String, DateTime, ForeignKey, func,Enum as SAEnum
from sqlalchemy.orm import relationship
from core.security import RoleEnum
from db.database import Base
import uuid

class StateModel(Base):
    __tablename__ = "states_master"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()), unique=True, nullable=False, index=True)
    state_name = Column(String(128), nullable=False, unique=True) # e.g. Karnataka
    state_code = Column(String(16), nullable=False, unique=True, index=True) # e.g. KA
    country_id = Column(String(36), ForeignKey("countries_master.id", ondelete="CASCADE"), nullable=False, index=True)

    # relationships 1 state has 1 country
    country = relationship("CountryModel", back_populates="states")
    # 1 State has many Regions
    regions = relationship("RegionModel", back_populates="state", cascade="all, delete-orphan", lazy="selectin")
    
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_modified = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now(), nullable=False)