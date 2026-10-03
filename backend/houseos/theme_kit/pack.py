"""`.houseos-theme` packs: a zip of one theme folder's data, with a checksum per file. Importing
never trusts anything compiled: the CSS is rebuilt from the tokens and every check runs again."""

import hashlib
import io
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path

from . import check as c, tokens as t

DATA = re.compile(r"^(theme\.json|tokens(\.(dark|light))?\.json|flavor\.json|sprites\.json|BRIEF\.md"
                  r"|art/[a-z0-9][a-z0-9._-]{0,60}\.(svg|png|webp)|fonts/[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.(woff2|txt|md))$")  # fmt: skip
MAX_PACK, MAX_FILES = 3_500_000, 60


def pack(theme_id: str, root: Path | None = None, out: Path | None = None) -> Path:
    root = root or t.ROOT
    folder = t.load(theme_id, root).folder
    files = sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())
    files = [name for name in files if DATA.fullmatch(name)]
    target = out or Path.cwd() / f"{theme_id}.houseos-theme"
    sums = {name: hashlib.sha256((folder / name).read_bytes()).hexdigest() for name in files}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for name in files:
            z.write(folder / name, name)
        z.writestr("checksums.json", json.dumps(sums, indent=2))
    return target


def manifest_of(data: bytes) -> dict:
    """A pack's theme.json, read before anything is installed (to know whose id it would take)."""
    if len(data) > MAX_PACK:
        raise t.ThemeError(f"A theme pack is {MAX_PACK // 1_000_000} MB at most")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if z.getinfo("theme.json").file_size > 20_000:
                raise t.ThemeError("theme.json is too large")
            manifest = json.loads(z.read("theme.json"))
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise t.ThemeError("Not a HouseOS theme pack") from None
    if not isinstance(manifest, dict):
        raise t.ThemeError("Not a HouseOS theme pack")
    return manifest


def unpack(data: bytes, root: Path, theme_id: str | None = None) -> tuple[str, c.Results]:
    """Install a pack into `root` (a runtime themes folder holding a copy of base). Returns the id
    and the check results; a pack that fails a check is not kept."""
    if len(data) > MAX_PACK:
        raise t.ThemeError(f"A theme pack is {MAX_PACK // 1_000_000} MB at most")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
        names = [i.filename for i in z.infolist() if not i.is_dir()]
        sums = json.loads(z.read("checksums.json"))
    except (zipfile.BadZipFile, KeyError, ValueError):
        raise t.ThemeError("Not a HouseOS theme pack") from None
    names = [n for n in names if n != "checksums.json"]
    if len(names) > MAX_FILES or sum(i.file_size for i in z.infolist()) > MAX_PACK * 2:
        raise t.ThemeError("This pack holds too much")
    for name in names:
        if not DATA.fullmatch(name):
            raise t.ThemeError(f"{name}: a theme pack holds only theme data (no code, CSS or other files)")
        if sums.get(name) != hashlib.sha256(z.read(name)).hexdigest():
            raise t.ThemeError(f"{name}: damaged (its checksum doesn't match)")
    manifest = json.loads(z.read("theme.json"))
    theme_id = theme_id or manifest.get("id", "")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", theme_id) or theme_id == "base":
        raise t.ThemeError("The pack's id is not a usable theme id")
    with tempfile.TemporaryDirectory(dir=root) as stage:
        folder = Path(stage) / theme_id
        for name in names:
            (folder / name).parent.mkdir(parents=True, exist_ok=True)
            (folder / name).write_bytes(z.read(name))
        manifest["id"] = theme_id
        (folder / "theme.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        t.copy_tree(root / "base", Path(stage) / "base")
        results, _ = c.check(theme_id, Path(stage))
        if not results.failed:
            shutil.rmtree(root / theme_id, ignore_errors=True)
            shutil.move(folder, root / theme_id)
    return theme_id, results
