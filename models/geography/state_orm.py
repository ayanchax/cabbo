from sqlalchemy import Column, Integer, String, Float
from db.database import Base


class GeoStateModel(Base):
    __tablename__ = "states_master"
    id = Column(Integer, primary_key=True, index=True)
    state_name = Column(String(64), unique=True, nullable=False)
    state_code = Column(String(8), unique=True, nullable=False)  # e.g. KA, TN
    permit_fee = Column(Float, nullable=False, default=0.0)
    is_home_state = Column(
        Integer, nullable=False, default=0
    )  # 1 for home state (e.g. KA), 0 for others


# Example: KA (Karnataka) is_home_state=1, permit_fee=0; TN (Tamil Nadu) is_home_state=0, permit_fee=700
