"""add orm indexes and trip fks

Revision ID: 4d2b7e8a9c10
Revises: 8fab71f323af
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql


# revision identifiers, used by Alembic.
revision: str = "4d2b7e8a9c10"
down_revision: Union[str, Sequence[str], None] = "8fab71f323af"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_trips_active_created", "trips", ["is_active", "created_at"])
    op.create_index(
        "ix_trips_active_status_created",
        "trips",
        ["is_active", "status", "created_at"],
    )
    op.create_index(
        "ix_trips_customer_bucket",
        "trips",
        ["creator_id", "creator_type", "is_active", "status", "start_datetime"],
    )
    op.create_index(
        "ix_trips_driver_status",
        "trips",
        ["driver_id", "is_active", "status"],
    )
    op.create_index(
        "ix_trips_type_status_start",
        "trips",
        ["trip_type_id", "status", "start_datetime"],
    )
    op.create_index(
        "ix_trip_status_audits_trip_timestamp",
        "trip_status_audits",
        ["trip_id", "timestamp"],
    )

    op.create_index("ix_drivers_name", "drivers", ["name"])
    op.create_index(
        "ix_drivers_active_available_created",
        "drivers",
        ["is_active", "is_available", "created_at"],
    )
    op.create_index(
        "ix_driver_earnings_driver_active_created",
        "driver_earnings",
        ["driver_id", "is_active", "created_at"],
    )
    op.create_index(
        "ix_trip_ratings_driver_flagged",
        "trip_ratings",
        ["driver_id", "is_flagged"],
    )
    op.create_index(
        "ix_trip_ratings_customer_flagged",
        "trip_ratings",
        ["customer_id", "is_flagged"],
    )

    op.create_index(
        "ix_customers_active_created",
        "customers",
        ["is_active", "created_at"],
    )
    op.create_index(
        "ix_customers_verification_flags",
        "customers",
        ["is_active", "is_phone_verified", "is_email_verified"],
    )
    op.create_index(
        "ix_pre_onboarding_expires_at",
        "pre_onboarding_customers",
        ["expires_at"],
    )
    op.create_index(
        "ix_pre_onboarding_customers_otp_hash",
        "pre_onboarding_customers",
        ["otp_hash"],
    )
    op.create_index(
        "ix_temp_trips_creator_created",
        "temp_trips",
        ["creator_id", "created_at"],
    )
    op.create_index(
        "ix_passengers_customer_active",
        "passengers",
        ["customer_id", "is_active"],
    )

    op.create_index(
        "ix_disputes_active_status_created",
        "disputes",
        ["is_active", "status", "created_at"],
    )
    op.create_foreign_key(
        "fk_disputes_entity_id_trips",
        "disputes",
        "trips",
        ["entity_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_trip_cancellations_active_created",
        "trip_cancellations",
        ["is_active", "created_at"],
    )
    op.create_foreign_key(
        "fk_trip_cancellations_entity_id_trips",
        "trip_cancellations",
        "trips",
        ["entity_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.alter_column(
        "refunds",
        "entity_id",
        existing_type=sa.String(length=255),
        type_=mysql.CHAR(length=36),
        existing_nullable=False,
    )
    op.create_index(
        "ix_refunds_active_status_created",
        "refunds",
        ["is_active", "refund_status", "created_at"],
    )
    op.create_foreign_key(
        "fk_refunds_entity_id_trips",
        "refunds",
        "trips",
        ["entity_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.create_index(
        "ix_outstation_pricing_available",
        "outstation_cab_pricing",
        ["is_available_in_network"],
    )
    op.create_index(
        "ix_outstation_pricing_state_available",
        "outstation_cab_pricing",
        ["state_id", "is_available_in_network"],
    )
    op.create_index(
        "ix_local_pricing_available",
        "local_cab_pricing",
        ["is_available_in_network"],
    )
    op.create_index(
        "ix_local_pricing_region_available",
        "local_cab_pricing",
        ["region_id", "is_available_in_network"],
    )
    op.create_index(
        "ix_airport_pricing_available",
        "airport_cab_pricing",
        ["is_available_in_network"],
    )
    op.create_index(
        "ix_airport_pricing_region_available",
        "airport_cab_pricing",
        ["region_id", "is_available_in_network"],
    )
    op.create_index("ix_permit_fee_state", "permit_fee_config", ["state_id"])

    op.create_index(
        "ix_support_contacts_active_type_created",
        "support_contacts",
        ["is_active", "support_type", "created_at"],
    )
    op.create_index(
        "ix_support_rule_lookup",
        "support_routing_rules",
        ["is_active", "scope_type", "scope_id", "trip_type_scope", "priority"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_support_rule_lookup", table_name="support_routing_rules")
    op.drop_index(
        "ix_support_contacts_active_type_created",
        table_name="support_contacts",
    )

    op.drop_index("ix_permit_fee_state", table_name="permit_fee_config")
    op.drop_index(
        "ix_airport_pricing_region_available",
        table_name="airport_cab_pricing",
    )
    op.drop_index("ix_airport_pricing_available", table_name="airport_cab_pricing")
    op.drop_index("ix_local_pricing_region_available", table_name="local_cab_pricing")
    op.drop_index("ix_local_pricing_available", table_name="local_cab_pricing")
    op.drop_index(
        "ix_outstation_pricing_state_available",
        table_name="outstation_cab_pricing",
    )
    op.drop_index(
        "ix_outstation_pricing_available",
        table_name="outstation_cab_pricing",
    )

    op.drop_constraint("fk_refunds_entity_id_trips", "refunds", type_="foreignkey")
    op.drop_index("ix_refunds_active_status_created", table_name="refunds")
    op.alter_column(
        "refunds",
        "entity_id",
        existing_type=mysql.CHAR(length=36),
        type_=sa.String(length=255),
        existing_nullable=False,
    )

    op.drop_constraint(
        "fk_trip_cancellations_entity_id_trips",
        "trip_cancellations",
        type_="foreignkey",
    )
    op.drop_index(
        "ix_trip_cancellations_active_created",
        table_name="trip_cancellations",
    )

    op.drop_constraint("fk_disputes_entity_id_trips", "disputes", type_="foreignkey")
    op.drop_index("ix_disputes_active_status_created", table_name="disputes")

    op.drop_index("ix_passengers_customer_active", table_name="passengers")
    op.drop_index("ix_temp_trips_creator_created", table_name="temp_trips")
    op.drop_index(
        "ix_pre_onboarding_customers_otp_hash",
        table_name="pre_onboarding_customers",
    )
    op.drop_index(
        "ix_pre_onboarding_expires_at",
        table_name="pre_onboarding_customers",
    )
    op.drop_index("ix_customers_verification_flags", table_name="customers")
    op.drop_index("ix_customers_active_created", table_name="customers")

    op.drop_index("ix_trip_ratings_customer_flagged", table_name="trip_ratings")
    op.drop_index("ix_trip_ratings_driver_flagged", table_name="trip_ratings")
    op.drop_index(
        "ix_driver_earnings_driver_active_created",
        table_name="driver_earnings",
    )
    op.drop_index("ix_drivers_active_available_created", table_name="drivers")
    op.drop_index("ix_drivers_name", table_name="drivers")

    op.drop_index(
        "ix_trip_status_audits_trip_timestamp",
        table_name="trip_status_audits",
    )
    op.drop_index("ix_trips_type_status_start", table_name="trips")
    op.drop_index("ix_trips_driver_status", table_name="trips")
    op.drop_index("ix_trips_customer_bucket", table_name="trips")
    op.drop_index("ix_trips_active_status_created", table_name="trips")
    op.drop_index("ix_trips_active_created", table_name="trips")
