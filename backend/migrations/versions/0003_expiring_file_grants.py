"""Allow exact recipient file grants to expire; existing grants remain permanent."""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("file_grants", sa.Column("expires_at", sa.DateTime(), nullable=True))
    op.create_index("ix_file_grants_expires_at", "file_grants", ["expires_at"])


def downgrade():
    raise RuntimeError("Use the documented isolated HouseOS restore procedure")
