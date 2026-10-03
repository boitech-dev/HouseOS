"""Hello, house: the example of docs/CUSTOM-INTEGRATIONS.md. It keeps the last link it is given,
from a phone shortcut (with a key), Capture's share button or Nox (after a confirmation card),
and shows it on its Control Room card. Copy this folder to start your own."""

import json
import time

from fastapi import APIRouter, Depends

from houseos.custom import Parts, Share


def setup(house):
    router = APIRouter()
    saved = house.folder / "last.json"

    def keep(url, actor, db):
        saved.write_text(json.dumps({"url": url, "by": actor.name, "at": time.time()}))
        house.record(db, "kept", {"by": actor.name}, actor)  # the diary: no private content
        db.commit()
        return {"status": "kept", "message": {"en": "Kept.", "fr": "Gardé."}}

    class Link(house.Input):
        url: str

    # A key route: a phone shortcut sends {"url": …} with "Authorization: Bearer <key>".
    @router.post("/keep")
    def keep_route(body: Link, actor=Depends(house.key_or_signed_in), db=Depends(house.get_db)):
        house.allowed(actor, "household.write")
        if not body.url.startswith(("https://", "http://")):
            raise house.problem(422, "HELLO_NOT_A_LINK", "That isn't a link.")
        return keep(body.url, actor, db)

    def last(actor, db):
        try:
            data = json.loads(saved.read_text())
        except (OSError, ValueError):
            return {"lines": [{"label": {"en": "Last link", "fr": "Dernier lien"}, "value": "—"}]}
        return {
            "lines": [
                {"label": {"en": "Last link", "fr": "Dernier lien"}, "value": data["url"], "tone": "success"}
            ],
            "help": [
                {
                    "en": "Share a link to HouseOS, then press Keep it.",
                    "fr": "Partage un lien vers HouseOS, puis Garde-le.",
                }
            ],
        }

    # Nox: "keep this link" → a card the person confirms → keep().
    def nox_keep(body, actor, db):
        return house.ask_first(actor, db, "keep", {"url": body.url}, "Keep this link", {"value": body.url})

    return Parts(
        router=router,
        key_routes=("/keep",),
        tools={"hello_keep": (Link, "Keep a link the person shares (a confirmation card).", nox_keep)},
        bundles=("general",),
        confirm={"keep": lambda data, actor, db: keep(data["url"], actor, db)},
        shares=[Share("keep", {"en": "Keep it", "fr": "Garde-le"}, r"^https?://", "/keep")],
        card=last,
    )
