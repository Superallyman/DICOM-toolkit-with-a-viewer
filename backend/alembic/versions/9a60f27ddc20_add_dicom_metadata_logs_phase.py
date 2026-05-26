from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "9a60f27ddc20"
down_revision = "df4f33a32b65"
branch_labels = None
depends_on = None


def upgrade():
    # 1) add column nullable so existing rows are OK
    op.add_column(
        "dicom_metadata_logs",
        sa.Column("phase", sa.String(length=10), nullable=True),
    )

    # 2) backfill existing rows
    op.execute("UPDATE dicom_metadata_logs SET phase = 'post' WHERE phase IS NULL")

    # 3) now make it NOT NULL
    op.alter_column(
        "dicom_metadata_logs",
        "phase",
        existing_type=sa.String(length=10),
        nullable=False,
    )

    # (if your autogen also created indexes, keep them here)
    op.create_index(
        "idx_dicom_metadata_study_phase",
        "dicom_metadata_logs",
        ["study_uid", "phase"],
        unique=False,
    )
    # if autogen added this simple study index too, include it:
    # op.create_index("ix_dicom_metadata_logs_study_uid", "dicom_metadata_logs", ["study_uid"], unique=False)

    # If autogen changed event_logs.message to Text, include this (optional if already Text):
    # op.alter_column("event_logs", "message", type_=sa.Text(), existing_type=sa.String(), existing_nullable=False)


def downgrade():
    # reverse the index/column changes
    # If you created ix_dicom_metadata_logs_study_uid above, drop it here too.
    # op.drop_index("ix_dicom_metadata_logs_study_uid", table_name="dicom_metadata_logs")
    op.drop_index("idx_dicom_metadata_study_phase", table_name="dicom_metadata_logs")
    op.drop_column("dicom_metadata_logs", "phase")
