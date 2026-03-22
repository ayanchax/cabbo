from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from db.database import yield_mysql_session
from services.seed_data_service import init_seed_data
from core.config import settings

router = APIRouter()


@router.get("/data")
def seed_data(
    secret: str= Query(..., description="Secret key to authorize data seeding"),
    db: Session = Depends(yield_mysql_session),
    
):  
    if secret != settings.CABBO_SUPER_ADMIN_SECRET:
        raise CabboException("You do not have permission to seed data.", status_code=403)
    
    return init_seed_data(db)
