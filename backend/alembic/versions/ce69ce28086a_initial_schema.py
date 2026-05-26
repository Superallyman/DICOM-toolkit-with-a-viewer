"""Initial schema

Revision ID: ce69ce28086a
Revises:
Create Date: 2025-06-12 21:32:08.291383
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "ce69ce28086a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # conversion_logs
    op.create_table(
        "conversion_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("input_file", sa.String(), nullable=False),
        sa.Column("output_file", sa.String(), nullable=True),
        sa.Column("format", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("study_uid", sa.String(), nullable=True),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("dicom_metadata", sa.JSON(), nullable=True),
        sa.Column("metadata_quality", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_conversion_logs_id", "conversion_logs", ["id"], unique=False)

    # event_logs
    op.create_table(
        "event_logs",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=True),
    )
    op.create_index("ix_event_logs_id", "event_logs", ["id"], unique=False)

    # dicom_metadata_logs
    op.create_table(
        "dicom_metadata_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("study_uid", sa.String(), nullable=False),
        sa.Column("sop_uid", sa.String(), nullable=False),
        sa.Column("series_uid", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # uid_path_mapping
    op.create_table(
        "uid_path_mapping",
        sa.Column("id", sa.String(), primary_key=True, nullable=False),
        sa.Column("study_uid", sa.String(), nullable=True),
        sa.Column("series_uid", sa.String(), nullable=True),
        sa.Column("sop_uid", sa.String(), nullable=True),
        sa.Column("study_hash", sa.String(), nullable=True),
        sa.Column("series_hash", sa.String(), nullable=True),
        sa.Column("sop_hash", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # thumbnails
    op.create_table(
        "thumbnails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("study_uid", sa.String(), nullable=False),
        sa.Column("series_uid", sa.String(), nullable=False),
        sa.Column("sop_uid", sa.String(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    # Optional seed (correct column names!)
    event_logs_table = sa.table(
        "event_logs",
        sa.column("event_type", sa.String()),
        sa.column("message", sa.Text()),
        sa.column("success", sa.Boolean()),
    )
    op.bulk_insert(
        event_logs_table,
        [{"event_type": "startup", "message": "System initialized.", "success": True}],
    )


def downgrade() -> None:
    op.drop_table("thumbnails")
    op.drop_table("uid_path_mapping")
    op.drop_table("dicom_metadata_logs")
    op.drop_index("ix_event_logs_id", table_name="event_logs")
    op.drop_table("event_logs")
    op.drop_index("ix_conversion_logs_id", table_name="conversion_logs")
    op.drop_table("conversion_logs")
