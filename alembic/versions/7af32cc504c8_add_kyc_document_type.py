"""add_kyc_document_type

Revision ID: 7af32cc504c8
Revises: 4d2b7e8a9c10
Create Date: 2026-08-01 15:41:38.977774

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


OLD_KYC_DOCUMENT_TYPES = (
    "aadhar_card",
    "pan_card",
    "driving_license",
    "passport",
    "voter_id",
    "vehicle_registration_certificate",
    "vehicle_insurance",
    "pollution_certificate",
    "bank_statement",
    "utility_bill",
)

NEW_KYC_DOCUMENT_TYPES = (
    *OLD_KYC_DOCUMENT_TYPES[:8],
    "fitness_certificate",
    *OLD_KYC_DOCUMENT_TYPES[8:],
)


# revision identifiers, used by Alembic.
revision: str = '7af32cc504c8'
down_revision: Union[str, Sequence[str], None] = '4d2b7e8a9c10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "kyc_document_types",
        "document_type",
        existing_type=sa.Enum(*OLD_KYC_DOCUMENT_TYPES, name="kycdocumenttypeenum"),
        type_=sa.Enum(*NEW_KYC_DOCUMENT_TYPES, name="kycdocumenttypeenum"),
        existing_nullable=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "kyc_document_types",
        "document_type",
        existing_type=sa.Enum(*NEW_KYC_DOCUMENT_TYPES, name="kycdocumenttypeenum"),
        type_=sa.Enum(*OLD_KYC_DOCUMENT_TYPES, name="kycdocumenttypeenum"),
        existing_nullable=False,
    )
