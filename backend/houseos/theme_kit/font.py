"""Fonts for a theme: an OFL family from Fontsource, copied into the theme's `fonts/` with its licence.

Only the Latin and Latin Extended files (French needs œ « » ’) of the weights asked, as woff2, named
`<family-slug>-<subset>-<weight>-<style>.woff2` (what the checks and the CSS expect), and the
family's own `OFL.txt` from Google Fonts' repository beside them."""

import json
import re
import urllib.parse
import urllib.request
from collections.abc import Callable
from pathlib import Path

from .tokens import ThemeError

API = "https://api.fontsource.org/v1/fonts/{id}"
LICENCE = "https://raw.githubusercontent.com/google/fonts/main/ofl/{name}/OFL.txt"
SUBSETS = ("latin", "latin-ext")
FILE_MAX = 400_000


# The only places fonts come from; nothing a model or a web page chose.
HOSTS = {"api.fontsource.org", "cdn.jsdelivr.net", "raw.githubusercontent.com"}


class Pinned(urllib.request.HTTPRedirectHandler):
    """Redirects only to HTTPS on the same allowed hosts."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        allowed(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def allowed(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in HOSTS or parts.port not in (None, 443):
        raise ThemeError(f"{url}: fonts come only from Fontsource, jsDelivr and Google Fonts' repository")
    return url


def download(url: str, limit: int) -> bytes:
    """A size-capped HTTPS GET from the font hosts only (the API process fetches these; the
    addresses are fixed, never taken from a conversation or a page)."""
    opener = urllib.request.build_opener(Pinned)
    with opener.open(
        urllib.request.Request(allowed(url), headers={"User-Agent": "HouseOS"}), timeout=20
    ) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        raise ThemeError(f"{url}: larger than {limit // 1000} KB")
    return data


def slug(family: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", family.lower()).strip("-")


def add(
    folder: Path,
    fontsource_id: str,
    weights=(400, 700),
    italic=False,
    get: Callable[[str, int], bytes] = download,
) -> str:
    """Copy a family into `folder/fonts`; returns its family name (for theme.json `fonts`)."""
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fontsource_id):
        raise ThemeError(f"{fontsource_id!r}: a Fontsource id looks like 'fraunces' or 'ibm-plex-sans'")
    try:
        meta = json.loads(get(API.format(id=fontsource_id), 2_000_000))
    except (OSError, ValueError) as error:  # ThemeError is a ValueError: a refused host says so
        raise ThemeError(f"{fontsource_id}: not found on Fontsource ({error})") from None
    family = meta.get("family", "")
    if not str(meta.get("license", "")).startswith("OFL"):
        raise ThemeError(f"{family or fontsource_id}: only fonts under the SIL Open Font License can be used")
    if not set(SUBSETS) <= set(meta.get("subsets", [])):
        raise ThemeError(f"{family}: has no Latin Extended files (French needs them)")
    missing = [w for w in weights if w not in meta.get("weights", [])]
    if missing:
        raise ThemeError(f"{family}: no weight {missing[0]} (it has {meta.get('weights')})")
    styles = ("normal", "italic") if italic and "italic" in meta.get("styles", []) else ("normal",)
    try:
        licence = get(LICENCE.format(name=re.sub(r"[^a-z0-9]", "", family.lower())), 100_000)
    except OSError:
        raise ThemeError(f"{family}: its licence file could not be fetched") from None
    fonts = folder / "fonts"
    fonts.mkdir(parents=True, exist_ok=True)
    name = slug(family)
    for weight in weights:
        for style in styles:
            for subset in SUBSETS:
                url = meta["variants"][str(weight)][style][subset]["url"]["woff2"]
                data = get(url, FILE_MAX)
                if not data.startswith(b"wOF2"):
                    raise ThemeError(f"{url}: not a woff2 font")
                (fonts / f"{name}-{subset}-{weight}-{style}.woff2").write_bytes(data)
    (fonts / f"{name}-OFL-LICENSE.txt").write_bytes(licence)
    return family
