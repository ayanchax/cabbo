from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_mysql_session
from utils.seed_data_generation import seed_pricing_master, seed_serviceable_geography, seed_states

router = APIRouter(prefix="/seed", tags=["seed"])


@router.get("/data")
def seed_data(
    db: Session = Depends(get_mysql_session),
):
    seed_states(db)
    seed_pricing_master(db)
    seed_serviceable_geography(db)
    return {"message": "Seed data generation completed successfully."}
