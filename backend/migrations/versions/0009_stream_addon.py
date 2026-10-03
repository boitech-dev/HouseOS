"""The film stream source is "a Stremio add-on you paste", no longer one named add-on: the stored
integration and the versions it listed in films in progress take neutral names. The pasted link
stays encrypted as it was. Data only; safe to run twice.

Revision ID: 0009
Revises: 0008
"""
import sqlalchemy as sa
from alembic import op

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None

OLD = {'name': 'torrentio', 'cached': '_torrentio_cached', 'filename': '_torrentio_filename', 'evidence': 'torrentio_cached'}
NEW = {'name': 'stream_addon', 'cached': '_addon_cached', 'filename': '_addon_filename', 'evidence': 'addon_cached'}
integrations = sa.table('integrations', sa.column('name', sa.String), sa.column('config', sa.JSON))


def renamed(value, old, new):
    if isinstance(value, list):
        return [renamed(v, old, new) for v in value]
    if not isinstance(value, dict):
        return value
    keys = {old['cached']: new['cached'], old['filename']: new['filename']}
    out = {keys.get(k, k): renamed(v, old, new) for k, v in value.items()}
    if out.get('provider') == old['name']:
        out['provider'] = new['name']
    if out.get('cache_evidence') == old['evidence']:
        out['cache_evidence'] = new['evidence']
    return out


def move(old, new):
    bind = op.get_bind()
    names = set(bind.execute(sa.select(integrations.c.name)).scalars())
    if old['name'] in names and new['name'] not in names:
        bind.execute(integrations.update().where(integrations.c.name == old['name']).values(name=new['name']))
    where = integrations.c.name == 'health_confirmed'
    confirmed = bind.execute(sa.select(integrations.c.config).where(where)).scalar()
    if confirmed and old['name'] in confirmed:
        confirmed = {new['name'] if k == old['name'] else k: v for k, v in confirmed.items()}
        bind.execute(integrations.update().where(where).values(config=confirmed))
    for name in ('cinema_workflows', 'cinema_confirmations'):
        table = sa.table(name, sa.column('id', sa.String), sa.column('data', sa.JSON))
        for id_, data in bind.execute(sa.select(table.c.id, table.c.data)).all():
            changed = renamed(data, old, new)
            if changed != data:
                bind.execute(table.update().where(table.c.id == id_).values(data=changed))


def upgrade():
    move(OLD, NEW)


def downgrade():
    move(NEW, OLD)
