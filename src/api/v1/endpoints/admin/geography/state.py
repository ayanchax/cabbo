from fastapi import APIRouter, Depends
from core.exceptions import CabboException
from core.exceptions import CabboException
from core.security import RoleEnum, validate_user_token
from db.database import a_yield_mysql_session
from models.geography.state_schema import StateSchema, StateUpdateSchema
from models.user.user_orm import User
from sqlalchemy.ext.asyncio import AsyncSession

from services.geography_service import (
    async_add_state,
    async_delete_state,
    async_get_all_states,
    async_update_state,
)

router = APIRouter()


# State Management
@router.post(
    "/add",
    response_model=StateSchema,
)
async def add_state(
    state: StateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Add a new state to the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to add states.", status_code=403
        )
    result = await async_add_state(payload=state, db=db, created_by=current_user_role)
    if not result:
        raise CabboException(status_code=500, detail="Failed to add new state")
    return result


@router.get(
    "/list",
    response_model=list[StateSchema],
)
def list_states(
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """List all states in the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [
        RoleEnum.super_admin,
        RoleEnum.driver_admin,
        RoleEnum.customer_admin,
    ]:
        raise CabboException(
            "You do not have permission to view states.", status_code=403
        )
    # Implementation to fetch and return list of states goes here
    return async_get_all_states(db=db)


@router.put(
    "/{state_id}",
    response_model=StateSchema,
)
async def update_state(
    state: StateUpdateSchema,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Update an existing state's configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to update states.", status_code=403
        )
    result, error = await async_update_state(payload=state, db=db)
    if error:
        raise CabboException(status_code=500, detail=error or "Failed to update state")
    return result


@router.delete("/{state_id}")
def delete_state(
    state_id: str,
    db: AsyncSession = Depends(a_yield_mysql_session),
    current_user: User = Depends(validate_user_token),
):
    """Delete a state from the system configuration."""
    current_user_role = current_user.role
    if current_user_role not in [RoleEnum.super_admin]:
        raise CabboException(
            "You do not have permission to delete states.", status_code=403
        )
    # Implementation to delete state goes here
    is_deleted, error = async_delete_state(state_id=state_id, db=db)
    if not is_deleted:
        raise CabboException(f"Failed to delete state: {error}", status_code=500)
    return {"detail": f"State {state_id} deleted successfully."}
