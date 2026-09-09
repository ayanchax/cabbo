"""remove_fuel_from_pricing_identity

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_fk_for_column(table_name: str, column_name: str) -> None:
    op.execute(
        f"""
        SET @fk_name := (
            SELECT constraint_name
            FROM information_schema.KEY_COLUMN_USAGE
            WHERE table_schema = DATABASE()
              AND table_name = '{table_name}'
              AND column_name = '{column_name}'
              AND referenced_table_name IS NOT NULL
            LIMIT 1
        )
        """
    )
    op.execute(
        f"""
        SET @drop_fk_sql := IF(
            @fk_name IS NOT NULL,
            CONCAT('ALTER TABLE {table_name} DROP FOREIGN KEY ', @fk_name),
            'SELECT 1'
        )
        """
    )
    op.execute("PREPARE drop_fk_stmt FROM @drop_fk_sql")
    op.execute("EXECUTE drop_fk_stmt")
    op.execute("DEALLOCATE PREPARE drop_fk_stmt")


def _drop_index_if_exists(table_name: str, index_name: str) -> None:
    op.execute(
        f"""
        SET @index_name := (
            SELECT index_name
            FROM information_schema.STATISTICS
            WHERE table_schema = DATABASE()
              AND table_name = '{table_name}'
              AND index_name = '{index_name}'
            LIMIT 1
        )
        """
    )
    op.execute(
        f"""
        SET @drop_index_sql := IF(
            @index_name IS NOT NULL,
            CONCAT('ALTER TABLE `{table_name}` DROP INDEX `', @index_name, '`'),
            'SELECT 1'
        )
        """
    )
    op.execute("PREPARE drop_index_stmt FROM @drop_index_sql")
    op.execute("EXECUTE drop_index_stmt")
    op.execute("DEALLOCATE PREPARE drop_index_stmt")


def _create_index_if_not_exists(table_name: str, index_name: str, columns: list[str]) -> None:
    column_sql = ", ".join(f"`{column}`" for column in columns)
    op.execute(
        f"""
        SET @index_name := (
            SELECT index_name
            FROM information_schema.STATISTICS
            WHERE table_schema = DATABASE()
              AND table_name = '{table_name}'
              AND index_name = '{index_name}'
            LIMIT 1
        )
        """
    )
    op.execute(
        f"""
        SET @create_index_sql := IF(
            @index_name IS NULL,
            'CREATE INDEX `{index_name}` ON `{table_name}` ({column_sql})',
            'SELECT 1'
        )
        """
    )
    op.execute("PREPARE create_index_stmt FROM @create_index_sql")
    op.execute("EXECUTE create_index_stmt")
    op.execute("DEALLOCATE PREPARE create_index_stmt")


def _collapse_pricing_table(table_name: str, jurisdiction_column: str, rate_column: str) -> None:
    op.execute(
        f"""
        CREATE TEMPORARY TABLE tmp_{table_name}_keep AS
        SELECT id
        FROM (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY {jurisdiction_column}, cab_type_id
                    ORDER BY {rate_column}, id
                ) AS row_number_in_group,
                COUNT(*) OVER (
                    PARTITION BY {jurisdiction_column}, cab_type_id
                ) AS group_count
            FROM {table_name}
        ) ranked
        WHERE row_number_in_group = FLOOR(group_count / 2) + 1
        """
    )
    op.execute(
        f"""
        UPDATE {table_name} pricing
        SET pricing.is_available_in_network = (
            SELECT grouped.available
            FROM (
                SELECT
                    {jurisdiction_column},
                    cab_type_id,
                    MAX(is_available_in_network) AS available
                FROM {table_name}
                GROUP BY {jurisdiction_column}, cab_type_id
            ) grouped
            WHERE grouped.{jurisdiction_column} = pricing.{jurisdiction_column}
              AND grouped.cab_type_id = pricing.cab_type_id
        )
        WHERE pricing.id IN (SELECT id FROM tmp_{table_name}_keep)
        """
    )
    op.execute(
        f"""
        DELETE pricing
        FROM {table_name} pricing
        LEFT JOIN tmp_{table_name}_keep keep_rows ON keep_rows.id = pricing.id
        WHERE keep_rows.id IS NULL
        """
    )
    op.execute(f"DROP TEMPORARY TABLE tmp_{table_name}_keep")


def _collapse_permit_fee_table() -> None:
    op.execute(
        """
        CREATE TEMPORARY TABLE tmp_permit_fee_config_keep AS
        SELECT id
        FROM (
            SELECT
                id,
                ROW_NUMBER() OVER (
                    PARTITION BY state_id, cab_type_id
                    ORDER BY permit_fee, id
                ) AS row_number_in_group,
                COUNT(*) OVER (
                    PARTITION BY state_id, cab_type_id
                ) AS group_count
            FROM permit_fee_config
        ) ranked
        WHERE row_number_in_group = FLOOR(group_count / 2) + 1
        """
    )
    op.execute(
        """
        DELETE permit
        FROM permit_fee_config permit
        LEFT JOIN tmp_permit_fee_config_keep keep_rows ON keep_rows.id = permit.id
        WHERE keep_rows.id IS NULL
        """
    )
    op.execute("DROP TEMPORARY TABLE tmp_permit_fee_config_keep")


def upgrade() -> None:
    """Upgrade schema."""
    _collapse_pricing_table(
        table_name="local_cab_pricing",
        jurisdiction_column="region_id",
        rate_column="hourly_rate",
    )
    _collapse_pricing_table(
        table_name="airport_cab_pricing",
        jurisdiction_column="region_id",
        rate_column="fare_per_km",
    )
    _collapse_pricing_table(
        table_name="outstation_cab_pricing",
        jurisdiction_column="state_id",
        rate_column="base_fare_per_km",
    )
    _collapse_permit_fee_table()

    _drop_fk_for_column("local_cab_pricing", "fuel_type_id")
    _drop_fk_for_column("airport_cab_pricing", "fuel_type_id")
    _drop_fk_for_column("outstation_cab_pricing", "fuel_type_id")
    _drop_fk_for_column("permit_fee_config", "fuel_type_id")

    _create_index_if_not_exists("local_cab_pricing", "ix_local_cab_pricing_region_id", ["region_id"])
    _create_index_if_not_exists("airport_cab_pricing", "ix_airport_cab_pricing_region_id", ["region_id"])
    _create_index_if_not_exists("outstation_cab_pricing", "ix_outstation_cab_pricing_state_id", ["state_id"])
    _create_index_if_not_exists("permit_fee_config", "ix_permit_fee_config_cab_type_id", ["cab_type_id"])
    _create_index_if_not_exists("permit_fee_config", "ix_permit_fee_config_state_id", ["state_id"])

    _drop_index_if_exists("local_cab_pricing", "uq_local_region_cab_fuel")
    _drop_index_if_exists("airport_cab_pricing", "uq_airport_region_cab_fuel")
    _drop_index_if_exists("outstation_cab_pricing", "uq_outstation_state_cab_fuel")
    _drop_index_if_exists("permit_fee_config", "uq_cab_fuel_state")

    op.drop_column("local_cab_pricing", "fuel_type_id")
    op.drop_column("airport_cab_pricing", "fuel_type_id")
    op.drop_column("outstation_cab_pricing", "fuel_type_id")
    op.drop_column("permit_fee_config", "fuel_type_id")

    op.create_unique_constraint(
        "uq_local_region_cab", "local_cab_pricing", ["region_id", "cab_type_id"]
    )
    op.create_unique_constraint(
        "uq_airport_region_cab", "airport_cab_pricing", ["region_id", "cab_type_id"]
    )
    op.create_unique_constraint(
        "uq_outstation_state_cab", "outstation_cab_pricing", ["state_id", "cab_type_id"]
    )
    op.create_unique_constraint(
        "uq_cab_state", "permit_fee_config", ["cab_type_id", "state_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_local_region_cab", "local_cab_pricing", type_="unique")
    op.drop_constraint("uq_airport_region_cab", "airport_cab_pricing", type_="unique")
    op.drop_constraint("uq_outstation_state_cab", "outstation_cab_pricing", type_="unique")
    op.drop_constraint("uq_cab_state", "permit_fee_config", type_="unique")

    op.add_column("local_cab_pricing", sa.Column("fuel_type_id", sa.CHAR(36), nullable=True))
    op.add_column("airport_cab_pricing", sa.Column("fuel_type_id", sa.CHAR(36), nullable=True))
    op.add_column("outstation_cab_pricing", sa.Column("fuel_type_id", sa.CHAR(36), nullable=True))
    op.add_column("permit_fee_config", sa.Column("fuel_type_id", sa.CHAR(36), nullable=True))

    op.execute(
        """
        SET @diesel_fuel_id := (
            SELECT id FROM fuel_types_master WHERE name = 'diesel' LIMIT 1
        )
        """
    )
    for table_name in (
        "local_cab_pricing",
        "airport_cab_pricing",
        "outstation_cab_pricing",
        "permit_fee_config",
    ):
        op.execute(f"UPDATE {table_name} SET fuel_type_id = @diesel_fuel_id")
        op.alter_column(table_name, "fuel_type_id", existing_type=sa.CHAR(36), nullable=False)
        op.create_foreign_key(
            f"fk_{table_name}_fuel_type_id",
            table_name,
            "fuel_types_master",
            ["fuel_type_id"],
            ["id"],
        )

    op.create_unique_constraint(
        "uq_local_region_cab_fuel",
        "local_cab_pricing",
        ["region_id", "cab_type_id", "fuel_type_id"],
    )
    op.create_unique_constraint(
        "uq_airport_region_cab_fuel",
        "airport_cab_pricing",
        ["region_id", "cab_type_id", "fuel_type_id"],
    )
    op.create_unique_constraint(
        "uq_outstation_state_cab_fuel",
        "outstation_cab_pricing",
        ["state_id", "cab_type_id", "fuel_type_id"],
    )
    op.create_unique_constraint(
        "uq_cab_fuel_state",
        "permit_fee_config",
        ["cab_type_id", "fuel_type_id", "state_id"],
    )
