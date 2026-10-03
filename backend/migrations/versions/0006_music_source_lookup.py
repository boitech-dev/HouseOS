"""Index the existing queue metadata cache for canonical-source display lookups.

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_music_source_latest', 'music_items', ['source_url', 'created_at'], mysql_length={'source_url': 191})


def downgrade():
    op.drop_index('ix_music_source_latest', table_name='music_items')
