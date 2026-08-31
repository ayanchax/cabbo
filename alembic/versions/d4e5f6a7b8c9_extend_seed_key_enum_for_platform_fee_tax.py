"""extend_seed_key_enum_for_platform_fee_tax

Revision ID: d4e5f6a7b8c9
Revises: cab3f4d5e6a7
Create Date: 2026-08-25 00:15:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "cab3f4d5e6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SEED_KEY_ENUM_WITH_PLATFORM_FEE_TAX = """
ENUM(
    'INITIAL_SEED_COMPLETED',
    'SEED_MASTER_DATA_V1',
    'SEED_GEO_CORE_V1',
    'SEED_GEO_REGIONS_V1',
    'SEED_SUPPORT_CONTACTS_V1',
    'SEED_PRICING_LOCAL_V1',
    'SEED_PRICING_OUTSTATION_V1',
    'SEED_PRICING_AIRPORT_V1',
    'SEED_PRICING_PLATFORM_V1',
    'SEED_TAX_PLATFORM_FEE_V1',
    'SEED_PRICING_NIGHT_V1',
    'SEED_PRICING_PERMIT_V1',
    'SEED_PRICING_CANCELLATION_POLICY_V1'
) NOT NULL
"""

SEED_KEY_ENUM_WITHOUT_PLATFORM_FEE_TAX = """
ENUM(
    'INITIAL_SEED_COMPLETED',
    'SEED_MASTER_DATA_V1',
    'SEED_GEO_CORE_V1',
    'SEED_GEO_REGIONS_V1',
    'SEED_SUPPORT_CONTACTS_V1',
    'SEED_PRICING_LOCAL_V1',
    'SEED_PRICING_OUTSTATION_V1',
    'SEED_PRICING_AIRPORT_V1',
    'SEED_PRICING_PLATFORM_V1',
    'SEED_PRICING_NIGHT_V1',
    'SEED_PRICING_PERMIT_V1',
    'SEED_PRICING_CANCELLATION_POLICY_V1'
) NOT NULL
"""


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        f"ALTER TABLE seed_metadata MODIFY COLUMN `key` {SEED_KEY_ENUM_WITH_PLATFORM_FEE_TAX}"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DELETE FROM seed_metadata WHERE `key` = 'SEED_TAX_PLATFORM_FEE_V1'")
    op.execute(
        f"ALTER TABLE seed_metadata MODIFY COLUMN `key` {SEED_KEY_ENUM_WITHOUT_PLATFORM_FEE_TAX}"
    )
