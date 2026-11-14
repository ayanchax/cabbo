"""Align early ledger installations with nullable historical capture values.

The first ledger migration was corrected before release, but some development
databases had already applied its earlier NOT NULL column definitions.
"""
from alembic import op
import sqlalchemy as sa

revision = "f9a0b1c2d3e4"
down_revision = "e8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade():
    columns = {column["name"]: column for column in
               sa.inspect(op.get_bind()).get_columns("platform_fee_collections")}
    for name in ("captured_at", "platform_fee_base", "platform_fee_tax"):
        column = columns[name]
        if not column["nullable"]:
            op.alter_column(
                "platform_fee_collections", name,
                existing_type=column["type"], existing_nullable=False,
                existing_comment=column.get("comment"), nullable=True,
            )


def downgrade():
    # The preceding migration now defines these columns as nullable too.
    # Retain that schema and never invent dates/tax values for historical rows.
    pass
