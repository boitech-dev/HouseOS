"""Allow inspecting an exact release before choosing its playback destination."""
from alembic import op
import sqlalchemy as sa
revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column('cinema_workflows', 'device_id', existing_type=sa.String(36), nullable=True)


def downgrade():
    raise RuntimeError('Device-free preparations must be reconciled before restoring the previous schema.')
