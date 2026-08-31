"""add_tax_configurations

Revision ID: cab3f4d5e6a7
Revises: 927acd1a8ead
Create Date: 2026-08-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "cab3f4d5e6a7"
down_revision: Union[str, Sequence[str], None] = "927acd1a8ead"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        ALTER TABLE seed_metadata
        MODIFY COLUMN `key` ENUM(
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
    )
    op.create_table(
        "tax_configurations",
        sa.Column("id", mysql.CHAR(length=36), nullable=False),
        sa.Column(
            "country_id",
            mysql.CHAR(length=36),
            nullable=False,
            comment="Country this tax configuration applies to.",
        ),
        sa.Column(
            "tax_type",
            sa.String(length=32),
            nullable=False,
            comment="Tax family, e.g. GST.",
        ),
        sa.Column(
            "tax_scope",
            sa.String(length=64),
            nullable=False,
            comment="Taxable charge scope, e.g. platform_fee.",
        ),
        sa.Column(
            "rate_percent",
            sa.Float(),
            nullable=False,
            comment="Tax rate percentage, e.g. 18.0 for 18% GST.",
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", mysql.CHAR(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_modified", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["country_id"], ["countries_master.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "country_id",
            "tax_type",
            "tax_scope",
            "effective_from",
            name="uq_tax_country_type_scope_effective_from",
        ),
    )
    op.create_index(op.f("ix_tax_configurations_id"), "tax_configurations", ["id"], unique=True)
    op.create_index(
        "ix_tax_country_scope_active",
        "tax_configurations",
        ["country_id", "tax_scope", "is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_tax_configurations_country_id"),
        "tax_configurations",
        ["country_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_tax_configurations_country_id"), table_name="tax_configurations")
    op.drop_index("ix_tax_country_scope_active", table_name="tax_configurations")
    op.drop_index(op.f("ix_tax_configurations_id"), table_name="tax_configurations")
    op.drop_table("tax_configurations")
    op.execute("DELETE FROM seed_metadata WHERE `key` = 'SEED_TAX_PLATFORM_FEE_V1'")
    op.execute(
        """
        ALTER TABLE seed_metadata
        MODIFY COLUMN `key` ENUM(
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
    )
