"""Add thumbnails table

Revision ID: df4f33a32b65
Revises: 6111d65805ac
Create Date: 2025-08-04 13:59:54.118240
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "df4f33a32b65"
down_revision = "6111d65805ac"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)

    table_name = "thumbnails"
    expected = {
        "id": postgresql.UUID(as_uuid=True),
        "study_uid": sa.String(),
        "series_uid": sa.String(),
        "sop_uid": sa.String(),
        "path": sa.Text(),
        "created_at": sa.DateTime(),
    }

    # Create the table if it doesn't exist
    if table_name not in insp.get_table_names():
        op.create_table(
            table_name,
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
            sa.Column("study_uid", sa.String(), nullable=False),
            sa.Column("series_uid", sa.String(), nullable=False),
            sa.Column("sop_uid", sa.String(), nullable=False),
            sa.Column("path", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
        return

    # If it does exist, ensure required columns are present (added as nullable to be safe)
    existing_cols = {c["name"] for c in insp.get_columns(table_name)}

    # Add any missing columns (nullable to avoid failures on non-empty tables)
    for col_name, col_type in expected.items():
        if col_name not in existing_cols:
            nullable = (col_name == "created_at") or (col_name == "id")  # be conservative
            op.add_column(table_name, sa.Column(col_name, col_type, nullable=nullable))

    # Ensure a primary key exists on "id"
    pk = insp.get_pk_constraint(table_name)
    if not pk or not pk.get("constrained_columns"):
        # Create a PK only if we don't have one; assume "id" now exists
        op.create_primary_key("pk_thumbnails", table_name, ["id"])


def downgrade() -> None:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if "thumbnails" in insp.get_table_names():
        op.drop_table("thumbnails")
