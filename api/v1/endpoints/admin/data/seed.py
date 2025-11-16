from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import get_mysql_session
from models.user.user_orm import User
from services.seed_data_service import init_seed_data
from services.user_service import get_user_by_id

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
    
    init_seed_data(db)
    return {"message": "Seed data generation completed successfully."}
