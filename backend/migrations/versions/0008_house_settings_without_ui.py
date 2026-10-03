"""House settings lose `ui` (the interface choice; Legacy is a theme): drop the stored key,
which the settings would now refuse. Data only; safe to run twice.

Revision ID: 0008
Revises: 0007
"""
import sqlalchemy as sa
from alembic import op

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None

integrations = sa.table('integrations', sa.column('name', sa.String), sa.column('config', sa.JSON))


def upgrade():
    bind = op.get_bind()
    where = integrations.c.name == 'house_settings'
    config = bind.execute(sa.select(integrations.c.config).where(where)).scalar()
    if config and 'ui' in config:
        bind.execute(integrations.update().where(where).values(config={k: v for k, v in config.items() if k != 'ui'}))


def downgrade():
    pass  # 3.9 reads a missing `ui` as its default
