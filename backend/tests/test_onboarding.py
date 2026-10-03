from test_core import admin


def test_welcome_dismissal_is_stored_per_account(client):
    c, _ = client
    admin(client)
    assert c.get("/api/v1/account/profile").json()["welcome_dismissed"] is False
    saved = c.patch("/api/v1/account/profile", json={"welcome_dismissed": True})
    assert saved.status_code == 200, saved.text
    assert saved.json()["welcome_dismissed"] is True
    # Other profile edits keep it; it can be turned back on.
    assert c.patch("/api/v1/account/profile", json={"language": "fr"}).json()["welcome_dismissed"] is True
    assert (
        c.patch("/api/v1/account/profile", json={"welcome_dismissed": False}).json()["welcome_dismissed"]
        is False
    )
    assert c.patch("/api/v1/account/profile", json={"welcome_dismissed": "later"}).status_code == 422
