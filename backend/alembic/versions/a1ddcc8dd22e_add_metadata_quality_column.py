"""Add metadata_quality column

Revision ID: a1ddcc8dd22e
Revises: e0a0ad3a30b5
Create Date: 2025-07-06 20:39:30.846110

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# top of file:
revision = "a1ddcc8dd22e"
down_revision = "e0a0ad3a30b5"
branch_labels = None
depends_on = None



def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("conversion_logs")}
    if "metadata_quality" not in cols:
        op.add_column("conversion_logs", sa.Column("metadata_quality", sa.String(), nullable=True))

def downgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    cols = {c["name"] for c in inspector.get_columns("conversion_logs")}
    if "metadata_quality" in cols:
        op.drop_column("conversion_logs", "metadata_quality")