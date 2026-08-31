"""prod_revision_bridge

Revision ID: d4e58a49cda2
Revises: 927acd1a8ead
Create Date: 2026-09-01 00:30:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "d4e58a49cda2"
down_revision: Union[str, Sequence[str], None] = "927acd1a8ead"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Prod was already stamped at this missing revision; no schema change."""
    pass


def downgrade() -> None:
    """No schema change to reverse."""
    pass
