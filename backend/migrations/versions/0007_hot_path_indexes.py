"""Index the music queue and event age; drop single-column indexes a composite already leads with.

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None

REDUNDANT = (
    ('ix_records_kind', 'records', 'kind'),
    ('ix_household_notifications_user_id', 'household_notifications', 'user_id'),
    ('ix_household_receipts_actor_id', 'household_receipts', 'actor_id'),
    ('ix_cinema_user_state_owner_id', 'cinema_user_state', 'owner_id'),
)


def upgrade():
    op.create_index('ix_music_queue', 'music_items', ['status', 'position'])
    op.create_index('ix_events_created_at', 'events', ['created_at'])
    for name, table, _ in REDUNDANT:
        op.drop_index(name, table_name=table)


def downgrade():
    for name, table, column in REDUNDANT:
        op.create_index(name, table, [column])
    op.drop_index('ix_events_created_at', table_name='events')
    op.drop_index('ix_music_queue', table_name='music_items')
