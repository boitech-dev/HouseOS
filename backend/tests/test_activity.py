from datetime import timedelta
from sqlalchemy import select
from houseos import core
from houseos.cinema_models import CinemaTitle, CinemaWorkflow
from houseos.db import new_id, utcnow
from houseos.models import Job, Operation


def test_activity_lists_only_my_recent_work_in_plain_codes(domain):
    db, (alice, bob, _) = domain
    title = CinemaTitle(
        id=new_id(), canonical_id="tt-" + new_id()[:8], title="Dune: Part Two", kind="movie", data={}
    )
    db.add(title)
    db.flush()
    op = Operation(
        id=new_id(), actor_id=alice.id, kind="cinema.discover", state="running", data={"media_id": title.id}
    )
    db.add(op)
    db.add(
        Job(
            logical_key="t:" + new_id(),
            kind="cinema.discover",
            actor_id=alice.id,
            state="running",
            payload={"operation_id": op.id},
        )
    )
    db.add(
        Job(
            logical_key="t:" + new_id(), kind="music.metadata", actor_id=alice.id, state="running", payload={}
        )
    )
    db.add(
        Job(logical_key="t:" + new_id(), kind="cinema.discover", actor_id=bob.id, state="running", payload={})
    )
    fresh = CinemaWorkflow(
        owner_id=alice.id,
        media_id=title.id,
        state="preparing",
        idempotency_key=new_id(),
        data={"_kind": "save_local", "download": {"bytes": 50, "total": 200}},
    )
    stale = CinemaWorkflow(
        owner_id=alice.id,
        media_id=title.id,
        state="command_sent",
        idempotency_key=new_id(),
        data={},
        updated_at=utcnow() - timedelta(hours=2),
    )
    db.add_all([fresh, stale])
    db.commit()
    items = core.activity(alice, db)["items"]
    assert sorted((i["kind"], i["title"]) for i in items) == [
        ("finding_sources", "Dune: Part Two"),
        ("saving_film", "Dune: Part Two"),
    ]
    assert next(i for i in items if i["kind"] == "saving_film")["progress"] == 0.25
    assert core.activity(bob, db)["items"][0]["kind"] == "finding_sources"  # only Bob's own job
    for row in db.scalars(select(CinemaWorkflow).where(CinemaWorkflow.owner_id == alice.id)):
        db.delete(row)
    db.flush()
    db.delete(title)
    db.commit()
