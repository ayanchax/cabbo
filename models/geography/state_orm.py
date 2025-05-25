from sqlalchemy import Column, Integer, String, Float, DateTime, func, Enum as SAEnum
from core.security import RoleEnum
from db.database import Base
import uuid


class GeoStateModel(Base):
    __tablename__ = "states_master"
    id = Column(
        String(36),  # Use String for UUID in MySQL
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        unique=True,
        nullable=False,
        index=True,
    )
    state_name = Column(String(64), unique=True, nullable=False)
    state_code = Column(String(8), unique=True, nullable=False)  # e.g. KA, TN
    permit_fee = Column(Float, nullable=False, default=0.0)
    is_home_state = Column(
        Integer, nullable=False, default=0
    )  # 1 for home state (e.g. KA), 0 for others
    created_by = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.system)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_modified = Column(
        DateTime(timezone=True),
        onupdate=func.now(),
        server_default=func.now(),
        nullable=False,
    )
