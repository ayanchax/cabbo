"""add_trip_upgradation_information

Revision ID: b6a1f7c2d9e4
Revises: a430ab6942b9
Create Date: 2026-08-02 12:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b6a1f7c2d9e4"
down_revision: Union[str, Sequence[str], None] = "a430ab6942b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "trips",
        sa.Column(
            "upgradation_information",
            sa.JSON(),
            nullable=True,
            comment="JSON/text for upgradation information, if any. This is applicable for scenarios where Cabbo upgrades the trip to a higher car type and/or fuel type or others. The upgradation information will be stored in this field as a JSON object with details of the upgradation and the additional charges, if any.",
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("trips", "upgradation_information")
