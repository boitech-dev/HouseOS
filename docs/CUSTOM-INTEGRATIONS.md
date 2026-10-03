# Your own integrations

Every house has something no one else has: a TV reached in a particular way, a script on another
computer, a device only you use. Your own integrations add that to HouseOS without changing it:
a git repository with a small manifest and a Python file, installed from **Control Room →
Integrations → Your own integrations**.

An integration can add:
- **routes** at `/api/v1/custom/<id>/…`, used by signed-in people or by its own **keys** (phone
  shortcuts, scripts, a helper on another computer: anything that can't sign in);
- **Nox tools**, in the bundles it chooses, with a confirmation card before acting;
- **share buttons** on Capture, for shared links that match its pattern (Android's share sheet
  → HouseOS);
- a **card** in Control Room: its status and how to use it.

> It runs inside HouseOS with the app's full rights: the house's data, its connections (Home
> Assistant…), the network. Install only code you wrote or trust. HouseOS shows what a repository
> holds before installing it, pins the exact commit, and keeps it off until an administrator
> turns it on.

## Installing one

1. **Control Room → Integrations → Add from a repository.** The repository's `https` address, a
   branch or tag if not the default, and for a private repository a **read-only access token**
   (kept encrypted; sent as a header, never written into the address or the copy).
2. **Check the repository** downloads it and reads its manifest. Nothing runs yet.
3. **Install, turned off**, then open it and turn it on. If it fails to start, it says why and
   the rest of the house carries on.

**Check for an update** downloads the branch again and shows the new commit; updating keeps its
keys, data and token. **Remove** deletes its code, keys and data (the activity diary keeps what it
wrote there). The Docker image includes `git`; a native install needs it installed.

## What a repository holds

```
houseos-integration.json
integration.py          (the entry; other modules beside it import relatively)
```

```json
{
  "id": "hello",
  "name": "Hello, house",
  "version": "1.0.0",
  "description": "One sentence for Control Room.",
  "entry": "integration.py"
}
```

`id`: lowercase letters, digits and `_`, 2 to 32 characters, starting with a letter. It names the
routes (`/api/v1/custom/hello/…`), the keys (`hos_hello_…`), the Nox tools (`hello_…`) and the
activity diary's lines (`custom.hello.…`).

The entry defines `setup(house)` and returns `Parts`. A complete, tested example is
[examples/hello-integration](examples/hello-integration/integration.py): copy it to start.

```python
from fastapi import APIRouter, Depends
from houseos.custom import Parts, Share

def setup(house):
    router = APIRouter()

    class Link(house.Input):
        url: str

    @router.post("/keep")
    def keep(body: Link, actor=Depends(house.key_or_signed_in), db=Depends(house.get_db)):
        house.allowed(actor, "household.write")
        ...
        return {"status": "kept"}

    return Parts(router=router, key_routes=("/keep",), shares=[Share("keep", "Keep it", r"^https?://", "/keep")])
```

Request models defined inside `setup()` (like `Link` above) need their type hints evaluated:
don't put `from __future__ import annotations` in the entry file, or FastAPI reads the body as a
query parameter and answers 422.

Python's standard library and what HouseOS itself uses (FastAPI, pydantic, httpx, SQLAlchemy…)
are available; an integration can't install other packages.

## `Parts`

| Field | What it is |
|---|---|
| `router` | A FastAPI `APIRouter`, served at `/api/v1/custom/<id>`. |
| `key_routes` | Path prefixes (`"/keep"`) that accept a key **without the browser's Origin**. Only these. |
| `tools` | `{"<id>_name": (InputModel, description, handler(body, actor, db))}` for Nox. |
| `bundles` | Which Nox bundles get the tools: `"general"` (default), `"tv"`, `"home"`, `"music"`… never setup mode. |
| `confirm` | `{action: handler(data, actor, db)}`: runs when a card from `house.ask_first(…, action, …)` is confirmed, once. |
| `shares` | `Share(id, label, match, path, field="url")`: a Capture button for text matching `match` (a regular expression JavaScript and Python both read); it POSTs `{field: text}` to `path`. |
| `card` | `card(actor, db) → {"lines": [{"label", "value", "tone"}], "help": [step, …]}` for Control Room. `tone`: `neutral`, `success`, `warning`, `danger`, `info`. |

Words people see (labels, card lines, help steps, a reply's `message`) can be a string or
`{"en": "…", "fr": "…"}`: HouseOS shows the person's language, else English.

## `house`: what HouseOS gives an integration

This is the stable surface; rely on nothing else in HouseOS.

| | |
|---|---|
| `house.id`, `house.folder` | Its id; its private folder for data (kept across updates, removed with it). |
| `Depends(house.get_db)` | The house's database session. |
| `Depends(house.signed_in)` | The signed-in person (an `Actor`: `id`, `name`, `role`, `permissions`). |
| `Depends(house.key_or_signed_in)` | One of its keys when the request sends one, else the sign-in. For key routes. |
| `Depends(house.key_only)` | One of its keys, never a sign-in (a helper's routes). |
| `house.allowed(actor, *permissions)` | Admins, or anyone with one of these permissions; else 403. |
| `house.home_assistant(db)` | `.states()`, `.state(id)`, `.exposed(id)`, `.call(domain, service, data)`; only the entities HouseOS may see (Smart home). |
| `house.record(db, event, payload, actor)` | A line in the activity diary (`custom.<id>.<event>`); no private content. |
| `house.ask_first(actor, db, action, data, label, preview)` | A Nox confirmation card. |
| `house.problem(status, code, message)` | An error with a sentence a person can act on. |
| `house.Input` | Base for request bodies (unknown fields refused). |

## Keys

Created on the integration's sheet in Control Room, one per use ("My phone", "The PC's
helper"): shown once, kept only as a hash, each removable on its own. A key acts as the
administrator who created it, as long as that account is an administrator, and opens only that
integration's routes; HouseOS waives the browser's Origin check only for the `key_routes` it
declares, and only when the request carries an `Authorization` header (no browser can forge one
across sites). Callers send `Authorization: Bearer <key>`.

## Testing yours

With a HouseOS checkout: put your folder on disk and use the same fixtures HouseOS's own test
does (`backend/tests/test_custom_integrations.py`): `custom_admin.install_folder(…)`, turn it on
through `/api/v1/admin/custom-integrations/<id>/enabled`, then call your routes with the
`client` fixture. Fake what reaches outside (Home Assistant, other computers).

## Where the code is

`backend/houseos/custom.py` (the `house` surface, loading, keys, serving, Nox),
`backend/houseos/custom_admin.py` (git, install, update, remove),
`frontend/src/custom_integrations.tsx` (Control Room and Capture's buttons). Sources are a field
(`"git"` today) so other ways in can come later, such as an integration Nox drafts with you,
through `custom_admin.install_folder`.
