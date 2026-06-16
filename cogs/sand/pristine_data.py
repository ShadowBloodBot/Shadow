"""In-game Pristine turret upgrade costs — sourced from workshop UI, not sandgame.wiki."""

from __future__ import annotations

import json
from pathlib import Path

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
PRISTINE_RECIPES_PATH = _DATA_DIR / "sand_pristine_recipes.json"


def merge_pristine_into_knowledge(knowledge: dict) -> dict:
    """Inject verified in-game Pristine upgrade recipes into knowledge."""
    if not PRISTINE_RECIPES_PATH.is_file():
        return knowledge

    with open(PRISTINE_RECIPES_PATH, encoding="utf-8") as f:
        pdata = json.load(f)

    shared = pdata.get("shared_inputs") or []
    if not shared:
        return knowledge

    workbench = pdata.get("workbench", "S&H Armaments Workshop")
    source = pdata.get("source", "in_game_ui")
    verified = pdata.get("verified_at")
    outputs = pdata.get("outputs") or []

    recipes = [r for r in knowledge.get("recipes", []) if "(Pristine)" not in r.get("output", "")]
    pristine_recipes: list[dict] = []
    for output in outputs:
        entry = {
            "output": output,
            "workbench": workbench,
            "inputs": [dict(i) for i in shared],
            "source": source,
        }
        if verified:
            entry["verified_at"] = verified
        pristine_recipes.append(entry)
        recipes.append(entry)

    knowledge["recipes"] = recipes

    by_output = {r["output"]: r for r in pristine_recipes}
    for item in knowledge.get("items", []):
        name = item.get("name")
        if name not in by_output:
            continue
        recipe = by_output[name]
        item["craft_recipe_text"] = " + ".join(f"{i['qty']} {i['item']}" for i in recipe["inputs"])
        item["craft_workbench"] = recipe["workbench"]
        item["craft_source"] = source

    meta = knowledge.setdefault("meta", {})
    sources = meta.setdefault("sources", [])
    if source not in sources:
        sources.append(source)

    return knowledge
