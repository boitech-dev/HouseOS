"""Remix: make a theme by hand in the app, no AI needed (the Workshop's editor).

A thin layer over the studio's own functions (tool_themes): the same drafts, the same checks, the
same rules (a person's drafts are their own; an administrator shares). The editor sends whole files
as JSON objects; a preview compiles them without saving; pictures are re-encoded here, never kept as
uploaded."""

import io
import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import Field

from . import themes, tool_themes as studio
from .auth import Actor, Input, require_admin
from .db import get_db
from .events import emit
from .theme_kit import build, check as kit_check, tokens as t

router = APIRouter(prefix="/themes/remix", tags=["themes"])
EDITABLE = (
    "theme.json",
    "tokens.json",
    "tokens.light.json",
    "tokens.dark.json",
    "flavor.json",
    "sprites.json",
)
UPLOAD_MAX = 10_000_000  # what a person may send; what is kept is re-encoded far smaller
SIDE_MAX = 1600


class Start(Input):
    source: str = Field(
        pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40, description="The theme to start from"
    )
    id: str = Field(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=40, description="The new draft's id")
    names: dict[str, str] = Field(description="Its name, en and fr")


class Draft(Input):
    theme: dict
    tokens: dict
    tokens_light: dict | None = None
    tokens_dark: dict | None = None
    flavor: dict | None = None
    sprites: dict | None = None


def source_folder(actor: Actor, theme_id: str) -> Path:
    # Base holds every token (sizes too): a theme starts from its templates, only what differs.
    if theme_id == "base":
        return t.ROOT / "_studio/templates"
    if theme_id in themes.bundled_ids():
        return t.ROOT / theme_id
    if not themes.visible(actor, theme_id):
        raise HTTPException(404, "No such theme")
    return themes.root() / theme_id


@router.post("")
def start(body: Start, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    """A new draft, a copy of any theme this person may see: then change what they like."""
    if not all(isinstance(body.names.get(lang), str) and body.names[lang].strip() for lang in ("en", "fr")):
        raise HTTPException(422, "A name in English and in French")
    source = source_folder(actor, body.source)
    if themes.meta(body.id):
        raise HTTPException(409, "You already have a theme with this id: choose another")

    def write(folder):
        for item in source.iterdir():
            if item.name in (*EDITABLE, "BRIEF.md") and item.is_file():
                shutil.copy2(item, folder / item.name)
            elif item.name in ("art", "fonts") and item.is_dir():
                t.copy_tree(item, folder / item.name)
        manifest = json.loads((folder / "theme.json").read_text())
        manifest.update(id=body.id, version=1, names={k: body.names[k][:32] for k in ("en", "fr")})
        if str((manifest.get("description") or {}).get("en", "")).startswith("One sentence:"):
            manifest["description"] = {
                "en": "Made by hand in the Workshop.",
                "fr": "Fait à la main dans l'Atelier.",
            }
        manifest.pop("hidden", None)
        manifest.pop("debug", None)
        manifest["author"] = actor.name[:80]
        (folder / "theme.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        if not (folder / "BRIEF.md").is_file():
            (folder / "BRIEF.md").write_text(
                f"# {body.names['en']}\n\nRemixed from {body.source} in the Workshop.\n"
            )

    result = studio.checked_write(actor, body.id, write)
    if result.get("passed"):
        emit(db, "themes.changed", {"id": body.id}, user_id=actor.id)
        db.commit()
    return result


@router.get("/fonts")
def fonts(actor: Actor = Depends(require_admin)):
    """The font catalogue (open licence, French letters), for the editor's type choices."""
    return {"fonts": json.loads((t.ROOT / "_studio/fonts.json").read_text())["fonts"]}


@router.get("/{theme_id}")
def files(theme_id: str, actor: Actor = Depends(require_admin)):
    """A draft's editable files (as JSON), its pictures and fonts: what the editor works on."""
    folder = studio.own_folder(actor, theme_id)
    data = {name: t.read(folder / name) or None for name in EDITABLE}
    art = sorted(p.name for p in (folder / "art").iterdir()) if (folder / "art").is_dir() else []
    return {
        "id": theme_id,
        "theme": data["theme.json"],
        "tokens": data["tokens.json"] or {},
        "tokens_light": data["tokens.light.json"],
        "tokens_dark": data["tokens.dark.json"],
        "flavor": data["flavor.json"],
        "sprites": data["sprites.json"],
        "art": art,
        "info": themes.public(actor, theme_id),
    }


def texts(body: Draft, brief: str) -> dict:
    dump = lambda value: json.dumps(value, indent=2, ensure_ascii=False) if value else None  # noqa: E731
    return {
        "theme_json": dump(body.theme),
        "tokens_json": dump(body.tokens) or "{}",
        "tokens_light_json": dump(body.tokens_light),
        "tokens_dark_json": dump(body.tokens_dark),
        "flavor_json": dump(body.flavor),
        "sprites_json": dump(body.sprites),
        "brief": brief,
    }


@router.put("/{theme_id}")
def save(theme_id: str, body: Draft, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    """Keep the draft if every check passes (else the exact failures, and nothing changes)."""
    folder = studio.own_folder(actor, theme_id)
    brief = (folder / "BRIEF.md").read_text() if (folder / "BRIEF.md").is_file() else f"# {theme_id}\n"
    result = studio.save(studio.Save(id=theme_id, **texts(body, brief[:6000])), actor, db)
    if result.get("passed"):
        emit(db, "themes.changed", {"id": theme_id}, user_id=actor.id)
        db.commit()
        result["info"] = themes.public(actor, theme_id)
    return result


@router.post("/{theme_id}/preview")
def preview(theme_id: str, body: Draft, actor: Actor = Depends(require_admin)):
    """The draft as it would be, compiled but not kept: its CSS (for a preview marked
    data-theme="<id>--preview"), what the interface knows of it, and what the checks say."""
    folder = studio.own_folder(actor, theme_id)
    with tempfile.TemporaryDirectory() as stage:
        stage = Path(stage)
        t.copy_tree(themes.root() / "base", stage / "base")
        t.copy_tree(themes.root() / "_schema", stage / "_schema")
        draft = stage / theme_id
        t.copy_tree(folder, draft, skip=("house.json", "theme.css"))
        for name, value in (
            ("theme.json", {**body.theme, "id": theme_id}),
            ("tokens.json", body.tokens),
            ("tokens.light.json", body.tokens_light),
            ("tokens.dark.json", body.tokens_dark),
            ("flavor.json", body.flavor),
            ("sprites.json", body.sprites),
        ):
            (draft / name).unlink(missing_ok=True)
            if value:
                (draft / name).write_text(json.dumps(value))
        try:
            theme, base = t.load(theme_id, stage), t.load("base", stage)
            css = build.theme_css(theme, base, f"/themes/{theme_id}/")
            fonts = build.font_faces(theme, f"/themes/{theme_id}/fonts/")
            info = build.entry(theme, base)
        except (t.ThemeError, KeyError, ValueError, TypeError, AttributeError) as error:
            return {"status": "invalid", "failures": [str(error)[:300]]}
        results, _ = kit_check.check(theme_id, stage)
    marked = css.replace(f'[data-theme="{theme_id}"]', f'[data-theme="{theme_id}--preview"]') + fonts
    info = build.served(info, f"/themes/{theme_id}/") | {"id": theme_id + "--preview"}
    return {"status": "compiled", "css": marked, "info": info, **studio.summary(results)}


@router.post("/{theme_id}/art")
def upload_art(
    theme_id: str,
    name: str = Form(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=30),
    pixel: bool = Form(False),
    file: UploadFile = File(...),
    actor: Actor = Depends(require_admin),
):
    """A picture for a slot. Re-encoded (no metadata, at most 1600 px): pixel art as PNG, kept
    crisp; anything else as WebP, made smaller until it fits the 200 KB budget."""
    from PIL import Image, UnidentifiedImageError

    studio.own_folder(actor, theme_id)
    raw = file.file.read(UPLOAD_MAX + 1)
    if len(raw) > UPLOAD_MAX:
        raise HTTPException(413, "A picture of 10 MB at most")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ("PNG", "JPEG", "WEBP", "GIF"):
            raise HTTPException(422, "A PNG, JPEG, WebP or GIF picture")
        image.load()
    except (UnidentifiedImageError, OSError):
        raise HTTPException(422, "That file isn't a picture") from None
    image = image.convert("RGBA")
    image.thumbnail((SIDE_MAX, SIDE_MAX), Image.NEAREST if pixel else Image.LANCZOS)
    out, ext = io.BytesIO(), "png" if pixel else "webp"
    if pixel:
        image.save(out, "PNG", optimize=True)
    else:
        # Lower the quality, then the size, until it fits (a busy photo ends smaller, never refused).
        while True:
            for quality in (86, 72, 58):
                out = io.BytesIO()
                image.save(out, "WEBP", quality=quality, method=5)
                if out.tell() <= kit_check.ART_MAX:
                    break
            if out.tell() <= kit_check.ART_MAX or max(image.size) < 320:
                break
            image = image.resize((image.width * 3 // 4, image.height * 3 // 4), Image.LANCZOS)
    if out.tell() > kit_check.ART_MAX:
        raise HTTPException(413, "Even made smaller, this picture is over 200 KB: try a simpler one")

    def write(folder):
        (folder / "art").mkdir(exist_ok=True)
        for old in (folder / "art").glob(f"{name}.*"):
            old.unlink()
        (folder / "art" / f"{name}.{ext}").write_bytes(out.getvalue())

    result = studio.checked_write(actor, theme_id, write)
    return {**result, "path": f"art/{name}.{ext}"}


@router.post("/{theme_id}/pattern")
def pattern(theme_id: str, body: studio.Pattern, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    if body.id != theme_id:
        raise HTTPException(422, "The id in the address and the body differ")
    return studio.pattern(body, actor, db)


@router.post("/{theme_id}/font")
def font(theme_id: str, body: studio.Font, actor: Actor = Depends(require_admin), db=Depends(get_db)):
    if body.id != theme_id:
        raise HTTPException(422, "The id in the address and the body differ")
    return studio.font(body, actor, db)
