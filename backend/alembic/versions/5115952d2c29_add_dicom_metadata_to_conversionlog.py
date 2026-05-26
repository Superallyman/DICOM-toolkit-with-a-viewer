from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "5115952d2c29"
down_revision = "ce69ce28086a"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("conversion_logs")}

    if "input_file" not in cols:
        op.add_column("conversion_logs", sa.Column("input_file", sa.String(), nullable=False))
    if "output_file" not in cols:
        op.add_column("conversion_logs", sa.Column("output_file", sa.String(), nullable=True))
    if "study_uid" not in cols:
        op.add_column("conversion_logs", sa.Column("study_uid", sa.String(), nullable=True))
    if "error" not in cols:
        op.add_column("conversion_logs", sa.Column("error", sa.String(), nullable=True))

    # make status NOT NULL if it isn’t already; ignore if already constrained
    try:
        op.alter_column("conversion_logs", "status", existing_type=sa.VARCHAR(), nullable=False)
    except Exception:
        pass

    # drop old column if it’s still there
    cols = {c["name"] for c in insp.get_columns("conversion_logs")}
    if "filename" in cols:
        op.drop_column("conversion_logs", "filename")

def downgrade():
    bind = op.get_bind()
    insp = inspect(bind)
    cols = {c["name"] for c in insp.get_columns("conversion_logs")}

    if "filename" not in cols:
        op.add_column("conversion_logs", sa.Column("filename", sa.VARCHAR(), nullable=True))
    try:
        op.alter_column("conversion_logs", "status", existing_type=sa.VARCHAR(), nullable=True)
    except Exception:
        pass
    for c in ("error", "study_uid", "output_file", "input_file"):
        cols = {x["name"] for x in insp.get_columns("conversion_logs")}
        if c in cols:
            op.drop_column("conversion_logs", c)
