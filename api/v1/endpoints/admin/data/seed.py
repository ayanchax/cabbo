from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import get_mysql_session
from models.user.user_orm import User
from services.user_service import get_user_by_id
from utils.seed_data_generation import seed_kyc_document_types, seed_pricing_master, seed_serviceable_geography, seed_states, seed_super_admin

router = APIRouter()


@router.get("/data")
def seed_data(
    db: Session = Depends(get_mysql_session),
    current_user: User = Depends(validate_user_token)
):  
    current_user_role = current_user.role
    user = get_user_by_id(user_id=current_user.id, db=db, active=True)

    if current_user_role!=user.role or current_user_role!=RoleEnum.super_admin or current_user.id!=user.id:
        raise CabboException("You do not have permission to seed data.", status_code=403)
    
    seed_states(db)
    seed_pricing_master(db)
    seed_serviceable_geography(db)
    seed_kyc_document_types(db)
    seed_super_admin(db)
    return {"message": "Seed data generation completed successfully."}
