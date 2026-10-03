from alembic import context
from houseos.db import Base, engine
from houseos import models, auth, music, household, files, cinema, notifications, assistant  # noqa: F401 (registers every model)

if engine is None:
    raise RuntimeError("Database connection must be provided through the protected environment")
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
