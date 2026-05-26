"""Add metadata_quality column

Revision ID: e0a0ad3a30b5
Revises: 3fafaa6dbc16
Create Date: 2025-07-06 20:05:22.012490

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e0a0ad3a30b5'
down_revision = '3fafaa6dbc16'
branch_labels = None
depends_on = None


from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'e0a0ad3a30b5'
down_revision = '3fafaa6dbc16'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    # Only add the column if the table exists and the column does not
    if 'dicom_metadata_logs' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('dicom_metadata_logs')}
        if 'metadata_quality' not in cols:
            op.add_column(
                'dicom_metadata_logs',
                sa.Column('metadata_quality', sa.String(), nullable=True)
            )

def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)

    if 'dicom_metadata_logs' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('dicom_metadata_logs')}
        if 'metadata_quality' in cols:
            op.drop_column('dicom_metadata_logs', 'metadata_quality')

