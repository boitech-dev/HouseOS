"""Persist request idempotency before conversation creation."""
from alembic import op
import sqlalchemy as sa
revision='0002'
down_revision='0001'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('chat_receipts',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('owner_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('request_key',sa.String(100),nullable=False),
        sa.Column('request_hash',sa.String(64),nullable=False),
        sa.Column('conversation_id',sa.String(36),sa.ForeignKey('records.id'),nullable=True),
        sa.Column('state',sa.String(30),nullable=False),
        sa.Column('result',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.UniqueConstraint('owner_id','request_key'))
    op.create_index('ix_chat_receipts_owner_id','chat_receipts',['owner_id'])


def downgrade():
    raise RuntimeError('Use the documented isolated HouseOS restore procedure')
