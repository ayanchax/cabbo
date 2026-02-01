"""rename driver orm column names

Revision ID: 7468d1b727cb
Revises: 0c2d89a1f6f3
Create Date: 2026-02-02 02:15:27.104355

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

# revision identifiers, used by Alembic.
revision: str = '7468d1b727cb'
down_revision: Union[str, Sequence[str], None] = '0c2d89a1f6f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    # Drop old columns
    

    # Update constraints
    #op.drop_index(op.f('car_registration_number'), table_name='drivers')
    op.create_unique_constraint(None, 'drivers', ['cab_registration_number'])


def downgrade() -> None:
    """Downgrade schema."""
    pass