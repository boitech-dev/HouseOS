"""Admins hear of each new batch of fixes, though the version number stays the same."""


def test_each_new_batch_of_changes_is_told_once(domain, monkeypatch):
    from houseos import house_actions, household
    from houseos.config import settings
    from houseos.models import User

    db, (alice, _, _) = domain
    db.get(User, alice.id).role = "admin"
    db.commit()
    told = []
    monkeypatch.setattr(settings, "storage_container", True)
    monkeypatch.setattr(
        household, "notify", lambda db, user, record, category, key: user == alice.id and told.append(key)
    )
    looks = iter([("1.0.0", "1.0.0", "abc123"), ("1.0.0", "1.0.0", "abc123"), ("1.0.0", "1.0.0", "def456")])
    monkeypatch.setattr(house_actions, "available", lambda: next(looks))
    for _ in range(3):
        house_actions.update_watch(db)
    db.commit()
    assert [k for k in told] == ["update:abc123", "update:def456"]
