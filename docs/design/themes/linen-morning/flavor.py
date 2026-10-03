"""Kinari's words: the house titles' names only (en, fr with tu), quiet and concrete.
    python3 docs/design/themes/linen-morning/flavor.py"""
import json, os
from pathlib import Path

OUT = Path(__file__).resolve().parents[4] / "themes/linen-morning/flavor.json"
T = {
    "dj": ("Keeper of the bell", "Gardien de la cloche"),
    "explorer": ("Mountain walker", "Marcheur des monts"),
    "night_owl": ("Moon viewer", "Qui regarde la lune"),
    "early_bird": ("First light", "Première lueur"),
    "weekend": ("Slow tea", "Thé sans hâte"),
    "genre_guardian": ("{genre}, kept with care", "{genre}, gardé avec soin"),
    "broken_record": ("The same stone, turned", "La même pierre, retournée"),
    "marathon": ("Long sitting", "Longue assise"),
    "radio_host": ("Voice of the house", "Voix de la maison"),
    "task_hero": ("Sweeper of the path", "Balayeur du chemin"),
    "grocery_runner": ("Market walker", "Marcheur du marché"),
    "planner": ("Keeper of days", "Gardien des jours"),
    "wall_poet": ("Brush on the wall", "Pinceau du mur"),
    "courier": ("Carrier of letters", "Porteur de lettres"),
    "curator": ("One branch, well placed", "Une branche bien posée"),
    "high_scorer": ("Full gourd", "Gourde pleine"),
    "collector": ("Shell gatherer", "Chercheur de coquillages"),
    "game_hopper": ("Spinning top", "Toupie"),
    "console_hopper": ("Many doors", "Mille portes"),
    "romhacker": ("Old iron key", "Vieille clé de fer"),
}
data = {"$description": "Kinari: the house titles' names, in the voice of a quiet room. English and French (tu)."}
for k, (en, fr) in T.items():
    assert len(en) <= 28 and len(fr) <= 28, k
    data[f"title.{k}.name"] = {"en": en, "fr": fr}
tmp = OUT.with_name(".flavor.json.tmp")
tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
os.replace(tmp, OUT)
print("wrote", OUT)
