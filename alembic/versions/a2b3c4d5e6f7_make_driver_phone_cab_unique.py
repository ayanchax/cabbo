"""Make driver phone and cab registration unique as a pair.

Revision ID: a2b3c4d5e6f7
Revises: f19ebc4e6790
"""
from alembic import op


revision = "a2b3c4d5e6f7"
down_revision = "f19ebc4e6790"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_drivers_phone_cab_registration",
        "drivers",
        ["phone", "cab_registration_number"],
    )
    op.drop_constraint("phone", "drivers", type_="unique")
    op.drop_constraint("cab_registration_number", "drivers", type_="unique")


def downgrade() -> None:
    # Requires resolving duplicate individual phones/cabs introduced after upgrade.
    op.create_unique_constraint("phone", "drivers", ["phone"])
    op.create_unique_constraint("cab_registration_number", "drivers", ["cab_registration_number"])
    op.drop_constraint("uq_drivers_phone_cab_registration", "drivers", type_="unique")
