"""Read-only: is anything live in the house right now? Run before restarting services.

    agent-secret-run db-houseos /opt/houseos/state/venvs/app/bin/python deploy/idle_check.py

Exit 0 when idle, 1 when music, a film, a preparation, background work or a chat reply is
in progress (the output says what). Never writes."""

import os
import sys
from sqlalchemy import create_engine, text

url = os.environ["DATABASE_URL"].replace("mysql://", "mysql+pymysql://", 1)
CHECKS = {
    "music playing or starting": "select count(*) from music_queue where desired = 'playing' and current_id is not null",
    "film on a screen": "select count(*) from cinema_workflows where state in ('playing_observed','paused','command_sent')",
    "film preparing": "select count(*) from cinema_workflows where state = 'preparing'",
    "preparation lane busy": "select count(*) from cinema_preparations where state in ('running','queued')",
    "background jobs running": "select count(*) from jobs where state = 'running'",
    "assistant replying": "select count(*) from chat_receipts where state = 'running'",
}
busy = []
with create_engine(url, hide_parameters=True).connect() as connection:
    connection.execute(text("SET SESSION TRANSACTION READ ONLY"))
    for label, query in CHECKS.items():
        count = connection.execute(text(query)).scalar()
        print(f"{label:28} {count}")
        if count:
            busy.append(label)
print("IDLE" if not busy else "BUSY: " + ", ".join(busy))
sys.exit(1 if busy else 0)
