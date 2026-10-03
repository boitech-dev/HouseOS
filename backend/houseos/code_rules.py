"""What a change drafted by Nox may touch, and the digest that ties Apply to the diff the admin read.

Standard library only: deploy/code_change.py (the house computer's side) loads this one file
from the running release, never the package (its __init__ would run drafted code outside the
jail); houseos.sh keeps the same rule in bash (tests/test_code_changes.py checks they agree). Nox
may change neither this file nor the package's __init__.py. Case-insensitive, like some disks."""

import hashlib
import re

NAME = "[A-Za-z0-9_-][A-Za-z0-9_.-]*"  # one path segment: never ".", ".." or a dot-file
# The app's code and tests, the screens, bundled themes' data, the top-level docs. Never what
# builds, checks, deploys or undoes a change (deploy/, packaging/, tools/, frontend/scripts,
# vite.config, themes/_kit), dependencies (pyproject, uv.lock, package*.json), migrations (Undo
# can't take a database back), conftest.py (it sets up every test), this file or __init__.py.
ALLOWED = re.compile(
    rf"backend/houseos/({NAME}/)*{NAME}\.py|backend/tests/({NAME}/)*{NAME}\.(py|json)"
    rf"|frontend/src/({NAME}/)*{NAME}\.(tsx?|css)|themes/[a-z0-9][a-z0-9-]*/({NAME}/)*{NAME}\.(json|md)"
    rf"|docs/{NAME}\.md",
    re.I | re.A,
)
LOCKED = re.compile(r"(^|/)conftest\.py$|^backend/houseos/(code_rules|__init__)\.py$", re.I | re.A)


def allowed(path):
    return bool(ALLOWED.fullmatch(path)) and not LOCKED.search(path)


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def digest(change):
    """Each file's path, text before and drafted text: exactly the diff the Changes page shows."""
    return sha(
        "".join(
            f"{path} {sha(change['before'].get(path, ''))} {sha(text)}\n"
            for path, text in sorted(change["files"].items())
        )
    )
