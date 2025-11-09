from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from db.database import get_mysql_session
from utils.seed_data_generation import seed_kyc_document_types, seed_pricing_master, seed_serviceable_geography, seed_states, seed_super_admin

router = APIRouter()


@router.get("/data")
def seed_data(
    db: Session = Depends(get_mysql_session),
):  
    
    seed_states(db)
    seed_pricing_master(db)
    seed_serviceable_geography(db)
    seed_kyc_document_types(db)
    seed_super_admin(db)
    return {"message": "Seed data generation completed successfully."}
