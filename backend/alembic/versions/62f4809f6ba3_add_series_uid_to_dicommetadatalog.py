from alembic import op
import sqlalchemy as sa

revision = '62f4809f6ba3'
down_revision = 'a1ddcc8dd22e'
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'dicom_metadata_logs' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('dicom_metadata_logs')}
        if 'series_uid' not in cols:
            op.add_column('dicom_metadata_logs', sa.Column('series_uid', sa.String(), nullable=True))

def downgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    if 'dicom_metadata_logs' in insp.get_table_names():
        cols = {c['name'] for c in insp.get_columns('dicom_metadata_logs')}
        if 'series_uid' in cols:
            op.drop_column('dicom_metadata_logs', 'series_uid')
