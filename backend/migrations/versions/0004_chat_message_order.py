"""Persist chronological message order for complete bounded history pagination."""
import json
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('chat_messages', sa.Column('sequence', sa.Integer(), nullable=True))
    connection = op.get_bind()
    conversations = connection.execute(sa.text('SELECT DISTINCT conversation_id FROM chat_messages')).scalars().all()
    for identity in conversations:
        raw = connection.execute(sa.text('SELECT data FROM records WHERE id=:id'), {'id':identity}).scalar()
        data = json.loads(raw) if isinstance(raw, str) else raw or {}
        tracked = data.get('message_ids', [])
        ordered = connection.execute(sa.text('SELECT id FROM chat_messages WHERE conversation_id=:id ORDER BY created_at,id'), {'id':identity}).scalars().all()
        valid = set(ordered)
        known = [item for item in tracked if item in valid]
        seen = set(known)
        ordered = [item for item in ordered if item not in seen] + list(dict.fromkeys(known))
        for sequence, message in enumerate(ordered, 1):
            connection.execute(sa.text('UPDATE chat_messages SET sequence=:sequence WHERE id=:id'), {'sequence':sequence,'id':message})
    op.create_unique_constraint('uq_chat_message_sequence', 'chat_messages', ['conversation_id','sequence'])


def downgrade():
    raise RuntimeError('Restore an isolated HouseOS backup; do not silently discard message ordering')
