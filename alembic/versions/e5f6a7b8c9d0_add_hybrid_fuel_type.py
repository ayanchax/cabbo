"""add_hybrid_fuel_type

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FUEL_TYPE_ENUM_WITH_HYBRID = "ENUM('diesel','petrol','cng','hybrid')"
FUEL_TYPE_ENUM_WITHOUT_HYBRID = "ENUM('diesel','petrol','cng')"


def upgrade() -> None:
    """Upgrade schema and seed Hybrid pricing from CNG economics."""
    op.execute(
        f"ALTER TABLE fuel_types_master MODIFY COLUMN name {FUEL_TYPE_ENUM_WITH_HYBRID} NOT NULL"
    )
    op.execute(
        f"ALTER TABLE drivers MODIFY COLUMN fuel_type {FUEL_TYPE_ENUM_WITH_HYBRID} NOT NULL DEFAULT 'diesel'"
    )
    op.execute(
        f"ALTER TABLE trips MODIFY COLUMN preferred_fuel_type {FUEL_TYPE_ENUM_WITH_HYBRID} NULL DEFAULT 'hybrid'"
    )
    op.execute(
        f"ALTER TABLE temp_trips MODIFY COLUMN preferred_fuel_type {FUEL_TYPE_ENUM_WITH_HYBRID} NULL DEFAULT 'hybrid'"
    )

    op.execute(
        """
        INSERT INTO fuel_types_master
            (id, name, created_by, created_at, last_modified, is_active)
        SELECT UUID(), 'hybrid', 'system', UTC_TIMESTAMP(), UTC_TIMESTAMP(), TRUE
        WHERE NOT EXISTS (
            SELECT 1 FROM fuel_types_master WHERE name = 'hybrid'
        )
        """
    )
    op.execute(
        """
        UPDATE fuel_types_master
        SET is_active = TRUE, last_modified = UTC_TIMESTAMP()
        WHERE name = 'hybrid'
        """
    )
    op.execute(
        """
        UPDATE fuel_types_master
        SET is_active = FALSE, last_modified = UTC_TIMESTAMP()
        WHERE name = 'cng'
        """
    )

    op.execute(
        """
        INSERT INTO local_cab_pricing
            (
                id, cab_type_id, fuel_type_id, hourly_rate,
                overage_amount_per_hour, overage_amount_per_km,
                is_available_in_network, region_id, created_by,
                created_at, last_modified
            )
        SELECT
            UUID(), cng_pricing.cab_type_id, hybrid_fuel.id, cng_pricing.hourly_rate,
            cng_pricing.overage_amount_per_hour, cng_pricing.overage_amount_per_km,
            TRUE, cng_pricing.region_id, 'system',
            UTC_TIMESTAMP(), UTC_TIMESTAMP()
        FROM local_cab_pricing cng_pricing
        JOIN fuel_types_master cng_fuel ON cng_fuel.id = cng_pricing.fuel_type_id
        JOIN fuel_types_master hybrid_fuel ON hybrid_fuel.name = 'hybrid'
        WHERE cng_fuel.name = 'cng'
          AND NOT EXISTS (
              SELECT 1
              FROM local_cab_pricing existing
              WHERE existing.region_id = cng_pricing.region_id
                AND existing.cab_type_id = cng_pricing.cab_type_id
                AND existing.fuel_type_id = hybrid_fuel.id
          )
        """
    )

    op.execute(
        """
        INSERT INTO airport_cab_pricing
            (
                id, cab_type_id, fuel_type_id, fare_per_km,
                overage_amount_per_km, is_available_in_network,
                region_id, created_by, created_at, last_modified
            )
        SELECT
            UUID(), cng_pricing.cab_type_id, hybrid_fuel.id, cng_pricing.fare_per_km,
            cng_pricing.overage_amount_per_km, TRUE,
            cng_pricing.region_id, 'system', UTC_TIMESTAMP(), UTC_TIMESTAMP()
        FROM airport_cab_pricing cng_pricing
        JOIN fuel_types_master cng_fuel ON cng_fuel.id = cng_pricing.fuel_type_id
        JOIN fuel_types_master hybrid_fuel ON hybrid_fuel.name = 'hybrid'
        WHERE cng_fuel.name = 'cng'
          AND NOT EXISTS (
              SELECT 1
              FROM airport_cab_pricing existing
              WHERE existing.region_id = cng_pricing.region_id
                AND existing.cab_type_id = cng_pricing.cab_type_id
                AND existing.fuel_type_id = hybrid_fuel.id
          )
        """
    )

    op.execute(
        """
        INSERT INTO outstation_cab_pricing
            (
                id, cab_type_id, fuel_type_id, base_fare_per_km,
                driver_allowance_per_day, min_included_km_per_day,
                is_available_in_network, overage_amount_per_km,
                state_id, created_by, created_at, last_modified
            )
        SELECT
            UUID(), cng_pricing.cab_type_id, hybrid_fuel.id, cng_pricing.base_fare_per_km,
            cng_pricing.driver_allowance_per_day, cng_pricing.min_included_km_per_day,
            TRUE, cng_pricing.overage_amount_per_km,
            cng_pricing.state_id, 'system', UTC_TIMESTAMP(), UTC_TIMESTAMP()
        FROM outstation_cab_pricing cng_pricing
        JOIN fuel_types_master cng_fuel ON cng_fuel.id = cng_pricing.fuel_type_id
        JOIN fuel_types_master hybrid_fuel ON hybrid_fuel.name = 'hybrid'
        WHERE cng_fuel.name = 'cng'
          AND NOT EXISTS (
              SELECT 1
              FROM outstation_cab_pricing existing
              WHERE existing.state_id = cng_pricing.state_id
                AND existing.cab_type_id = cng_pricing.cab_type_id
                AND existing.fuel_type_id = hybrid_fuel.id
          )
        """
    )

    op.execute(
        """
        INSERT INTO permit_fee_config
            (
                id, cab_type_id, fuel_type_id, state_id, permit_fee,
                created_by, created_at, last_modified
            )
        SELECT
            UUID(), cng_permit.cab_type_id, hybrid_fuel.id, cng_permit.state_id,
            cng_permit.permit_fee, 'system', UTC_TIMESTAMP(), UTC_TIMESTAMP()
        FROM permit_fee_config cng_permit
        JOIN fuel_types_master cng_fuel ON cng_fuel.id = cng_permit.fuel_type_id
        JOIN fuel_types_master hybrid_fuel ON hybrid_fuel.name = 'hybrid'
        WHERE cng_fuel.name = 'cng'
          AND NOT EXISTS (
              SELECT 1
              FROM permit_fee_config existing
              WHERE existing.state_id = cng_permit.state_id
                AND existing.cab_type_id = cng_permit.cab_type_id
                AND existing.fuel_type_id = hybrid_fuel.id
          )
        """
    )

    op.execute(
        """
        UPDATE local_cab_pricing pricing
        JOIN fuel_types_master fuel ON fuel.id = pricing.fuel_type_id
        SET pricing.is_available_in_network = FALSE
        WHERE fuel.name = 'cng'
        """
    )
    op.execute(
        """
        UPDATE airport_cab_pricing pricing
        JOIN fuel_types_master fuel ON fuel.id = pricing.fuel_type_id
        SET pricing.is_available_in_network = FALSE
        WHERE fuel.name = 'cng'
        """
    )
    op.execute(
        """
        UPDATE outstation_cab_pricing pricing
        JOIN fuel_types_master fuel ON fuel.id = pricing.fuel_type_id
        SET pricing.is_available_in_network = FALSE
        WHERE fuel.name = 'cng'
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE drivers SET fuel_type = 'diesel' WHERE fuel_type = 'hybrid'")
    op.execute(
        "UPDATE trips SET preferred_fuel_type = 'diesel' WHERE preferred_fuel_type = 'hybrid'"
    )
    op.execute(
        "UPDATE temp_trips SET preferred_fuel_type = 'diesel' WHERE preferred_fuel_type = 'hybrid'"
    )

    op.execute(
        """
        DELETE pricing
        FROM local_cab_pricing pricing
        JOIN fuel_types_master fuel ON fuel.id = pricing.fuel_type_id
        WHERE fuel.name = 'hybrid'
        """
    )
    op.execute(
        """
        DELETE pricing
        FROM airport_cab_pricing pricing
        JOIN fuel_types_master fuel ON fuel.id = pricing.fuel_type_id
        WHERE fuel.name = 'hybrid'
        """
    )
    op.execute(
        """
        DELETE pricing
        FROM outstation_cab_pricing pricing
        JOIN fuel_types_master fuel ON fuel.id = pricing.fuel_type_id
        WHERE fuel.name = 'hybrid'
        """
    )
    op.execute(
        """
        DELETE permit
        FROM permit_fee_config permit
        JOIN fuel_types_master fuel ON fuel.id = permit.fuel_type_id
        WHERE fuel.name = 'hybrid'
        """
    )
    op.execute("DELETE FROM fuel_types_master WHERE name = 'hybrid'")
    op.execute(
        """
        UPDATE fuel_types_master
        SET is_active = TRUE, last_modified = UTC_TIMESTAMP()
        WHERE name = 'cng'
        """
    )

    op.execute(
        f"ALTER TABLE drivers MODIFY COLUMN fuel_type {FUEL_TYPE_ENUM_WITHOUT_HYBRID} NOT NULL DEFAULT 'diesel'"
    )
    op.execute(
        f"ALTER TABLE trips MODIFY COLUMN preferred_fuel_type {FUEL_TYPE_ENUM_WITHOUT_HYBRID} NULL DEFAULT 'diesel'"
    )
    op.execute(
        f"ALTER TABLE temp_trips MODIFY COLUMN preferred_fuel_type {FUEL_TYPE_ENUM_WITHOUT_HYBRID} NULL DEFAULT 'diesel'"
    )
    op.execute(
        f"ALTER TABLE fuel_types_master MODIFY COLUMN name {FUEL_TYPE_ENUM_WITHOUT_HYBRID} NOT NULL"
    )
