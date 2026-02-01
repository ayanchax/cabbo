"""add booking_id in trips table

Revision ID: 0c2d89a1f6f3
Revises: da1b02eafe03
Create Date: 2026-01-27 01:23:46.822690

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0c2d89a1f6f3'
down_revision: Union[str, Sequence[str], None] = 'da1b02eafe03'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add the `booking_id` column to the `trips` table
    pass


def downgrade() -> None:
    """Downgrade schema."""
    # Remove the `booking_id` column from the `trips` table
    pass