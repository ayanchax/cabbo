#- outstation pricing by cab type, fuel type and state, Only super admin or fin_admin can do

from sqlalchemy.ext.asyncio import AsyncSession
from api.v1.endpoints.admin.airport import validate_user_token, a_yield_mysql_session
from fastapi import APIRouter, Depends
from core.exceptions import CabboException
from core.security import RoleEnum
from models.user.user_orm import User

router = APIRouter()