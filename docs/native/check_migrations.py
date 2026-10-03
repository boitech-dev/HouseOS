"""Prove the Alembic migrations build exactly the schema the models declare.

Rebuilds the isolated houseos_migrate database from nothing with `alembic upgrade head`,
then diffs it against the SQLAlchemy metadata. Refuses any other database.

    agent-secret-run db-houseos_migrate /opt/houseos/state/venvs/app/bin/python deploy/check_migrations.py
"""

import os
import subprocess
import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect, text

# deploy/ in a release, docs/native/ in the repository: the nearest folder holding backend/.
backend = next(p / "backend" for p in Path(__file__).resolve().parents if (p / "backend/houseos").is_dir())
url = os.environ["DATABASE_URL"].replace("mysql://", "mysql+pymysql://", 1)
engine = create_engine(url, hide_parameters=True)
if engine.url.database != "houseos_migrate":
    sys.exit("Refusing to rebuild anything but the houseos_migrate scratch database")

with engine.begin() as connection:
    connection.execute(text("SET FOREIGN_KEY_CHECKS=0"))
    for table in inspect(connection).get_table_names():
        connection.execute(text(f"DROP TABLE `{table}`"))
    connection.execute(text("SET FOREIGN_KEY_CHECKS=1"))

subprocess.run(
    [sys.executable, "-m", "alembic", "upgrade", "head"],
    cwd=backend,
    check=True,
    env={**os.environ, "DATABASE_URL": url, "PYTHONPATH": str(backend)},
)

sys.path.insert(0, str(backend))
os.environ["DATABASE_URL"] = url
from alembic.autogenerate import compare_metadata  # noqa: E402
from alembic.migration import MigrationContext  # noqa: E402
import houseos.main  # noqa: E402,F401 (registers every model)
from houseos.db import Base  # noqa: E402

with engine.connect() as connection:
    diff = compare_metadata(
        MigrationContext.configure(connection, opts={"compare_type": True}), Base.metadata
    )
for change in diff:
    print("DRIFT", change)
print(f"{len(Base.metadata.tables)} tables; {len(diff)} differences between migrations and models")
sys.exit(1 if diff else 0)
