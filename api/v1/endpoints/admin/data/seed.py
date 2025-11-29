from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from core.config import Settings
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import get_mysql_session
from models.user.user_orm import User
from services.seed_data_service import init_seed_data
from services.user_service import get_user_by_id

router = APIRouter()


@router.get("/data")
def seed_data(
    secret: str= Query(..., description="Secret key to authorize data seeding"),
    db: Session = Depends(get_mysql_session),
    
):  
    if secret != Settings.CABBO_SUPER_ADMIN_SECRET:
        raise CabboException("You do not have permission to seed data.", status_code=403)
    
    init_seed_data(db)
    return {"message": "Seed data generation completed successfully."}
