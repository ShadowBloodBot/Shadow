"""Offline SAND knowledge query engine — unit-testable, intent + fuzzy match + craft chains."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from .pristine_data import merge_pristine_into_knowledge

try:
    from rapidfuzz import fuzz, process

    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

_PKG_DIR = Path(__file__).resolve().parent
DEFAULT_KNOWLEDGE_PATH = _PKG_DIR.parent.parent / "data" / "sand_knowledge.json"

THEME_FOOTER = "ShadowSyn · sandgame.wiki + ShadowSyn guide · bloodletting"

INTENT_LABELS = {
    "get_pristine_turret": "Pristine turrets",
    "craft_item": "Crafting",
    "material_cost": "Materials",
    "where_to_loot": "Loot locations",
    "fort_raid": "Fort raid",
    "storm_dive": "Storm Dive / Dreadnaught",
    "general": "General guide",
}

MATCH_THRESHOLD = 55
SUGGEST_THRESHOLD = 40


def load_knowledge(path: Path | str | None = None) -> dict:
    p = Path(path) if path else DEFAULT_KNOWLEDGE_PATH
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return merge_pristine_into_knowledge(data)


def wiki_footer(knowledge: dict) -> str:
    meta = knowledge.get("meta", {})
    sources = ", ".join(meta.get("sources", ["sandgame.wiki"]))
    scraped = meta.get("scraped_at", "offline")[:10]
    return f"ShadowSyn · {sources} · scraped {scraped} · bloodletting"


def _normalize(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s/+.-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    if HAS_RAPIDFUZZ:
        return fuzz.token_set_ratio(a, b)
    return SequenceMatcher(None, a, b).ratio() * 100


def _expand_aliases(query: str, aliases: dict) -> str:
    q = _normalize(query)
    for canonical, names in aliases.items():
        for name in [canonical, *names]:
            n = _normalize(name)
            if n in q or q in n:
                return canonical
    return q


def _all_item_names(knowledge: dict) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for item in knowledge.get("items", []):
        name = item.get("name")
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    for recipe in knowledge.get("recipes", []):
        name = recipe.get("output")
        if name and name not in seen:
            names.append(name)
            seen.add(name)
    return names


def suggest_closest_matches(query: str, knowledge: dict, limit: int = 3) -> list[tuple[str, int]]:
    """Return [(name, score)] for friendly unknown-item errors."""
    expanded = _expand_aliases(query, knowledge.get("item_aliases", {}))
    names = _all_item_names(knowledge)
    if not names:
        return []

    if HAS_RAPIDFUZZ:
        hits = process.extract(expanded, names, scorer=fuzz.token_set_ratio, limit=limit)
        return [(name, int(score)) for name, score, _ in hits if score >= SUGGEST_THRESHOLD]

    scored = sorted(
        ((n, int(_similarity(expanded, _normalize(n)))) for n in names),
        key=lambda x: x[1],
        reverse=True,
    )
    return [(n, s) for n, s in scored[:limit] if s >= SUGGEST_THRESHOLD]


def resolve_item(query: str, knowledge: dict, min_score: int = MATCH_THRESHOLD) -> dict | None:
    """Fuzzy-match query to best item or recipe output."""
    aliases = knowledge.get("item_aliases", {})
    expanded = _expand_aliases(query, aliases)
    names = _all_item_names(knowledge)
    if not names:
        return None

    if HAS_RAPIDFUZZ:
        match = process.extractOne(expanded, names, scorer=fuzz.token_set_ratio)
        if not match or match[1] < min_score:
            return None
        best_name, score = match[0], int(match[1])
    else:
        scored = sorted(names, key=lambda n: _similarity(expanded, _normalize(n)), reverse=True)
        if not scored:
            return None
        best_name = scored[0]
        score = int(_similarity(expanded, _normalize(best_name)))
        if score < min_score * 0.8:
            return None

    record = None
    kind = "unknown"
    for item in knowledge.get("items", []):
        if item.get("name") == best_name:
            record = item
            kind = "item"
            break
    if record is None:
        for recipe in knowledge.get("recipes", []):
            if recipe.get("output") == best_name:
                record = recipe
                kind = "recipe"
                break
    if record is None:
        record = {"name": best_name}

    return {"kind": kind, "record": record, "matched_name": best_name, "score": score}


def detect_intent(query: str, knowledge: dict) -> str:
    q = _normalize(query)
    if "material" in q and ("for" in q or "need" in q or "cost" in q):
        return "material_cost"
    best = ("general", 0)
    for intent_def in knowledge.get("faq_intents", []):
        score = sum(1 for p in intent_def.get("patterns", []) if p in q)
        if score > best[1]:
            best = (intent_def["intent"], score)
    if best[1] > 0:
        return best[0]
    if any(w in q for w in ("material", "how many", "cost", "recipe")):
        return "material_cost"
    if any(w in q for w in ("craft", "make", "build")):
        return "craft_item"
    if any(w in q for w in ("where", "find", "loot", "farm", "get")):
        return "where_to_loot"
    if "pristine" in q and any(w in q for w in ("cannon", "turret", "autocannon", "naval", "40mm", "80mm", "70mm")):
        return "get_pristine_turret"
    return "general"


def _find_recipe_for(name: str, knowledge: dict) -> dict | None:
    raw_target = _normalize(name)

    for recipe in knowledge.get("recipes", []):
        out = recipe.get("output", "")
        if _normalize(out) == raw_target or _normalize(_canonical_ingredient(out)) == raw_target:
            return recipe

    target = raw_target
    aliases = knowledge.get("item_aliases", {})
    for canonical, names in aliases.items():
        if target == _normalize(canonical) or any(target == _normalize(n) for n in names):
            target = _normalize(canonical)
            break

    for recipe in knowledge.get("recipes", []):
        out = recipe.get("output", "")
        if _normalize(out) == target or _normalize(_canonical_ingredient(out)) == target:
            return recipe
        if target in _normalize(out):
            return recipe

    for item in knowledge.get("items", []):
        if _normalize(item.get("name", "")) == target and item.get("craft_recipe_text"):
            blob = f"{item['craft_recipe_text']} {item.get('where_to_obtain', '')}".lower()
            wb = "Advanced/Fort Workbench" if "fort" in blob else "Workbench"
            if item.get("craft_workbench"):
                wb = item["craft_workbench"]
            return {
                "output": item["name"],
                "workbench": wb,
                "inputs": _parse_recipe_text(item["craft_recipe_text"]),
                "craft_recipe_text": item["craft_recipe_text"],
            }
    return None


INGREDIENT_ALIASES = {
    "petros": "1874 Petros",
    "1874e petros rifle": "1874 Petros",
    "1874 petros rifle": "1874 Petros",
    "sniper": "1874 Petros Sniper",
    "1874s petros sniper rifle": "1874 Petros Sniper",
    "silenced": "1874 Petros Silenced",
    "1874e/sd petros rifle (silenced)": "1874 Petros Silenced",
    "1874s/sd petros sniper rifle (silenced)": "1874 Petros Sniper Silenced",
    "rods": "Metal Rods",
    "metal rods": "Metal Rods",
    "lenses": "Optic Lenses",
    "optic lenses": "Optic Lenses",
    "weapon parts": "Weapon Parts",
    "scrap metal": "Scrap Metal",
    "parts": "Scrap Metal",
    "fabric": "Fabric",
    "fabric scraps": "Fabric Scraps",
    "gunpowder": "Gunpowder",
    "hggunpowder": "High-Grade Gunpowder",
    "high-grade gunpowder": "High-Grade Gunpowder",
    "scrapped ammo": "Scrapped Ammo",
    "ammo scraps": "Scrapped Ammo",
    "zseb": "EB Revolver Zseb",
    "eb zseb revolver": "EB Revolver Zseb",
    "drobulet shotgun": "Drobulet",
    "blitz pps-5 pistol": "Blitz Pistol PPS-5",
    "blitz 10r pistol": "Blitz Pistol 10R",
}

FORT_PREP_ITEMS = [
    "Time Bomb",
    "40mm Shell",
    "80mm Shell",
    "70mm Shell",
]

PRISTINE_AMMO = {
    "40mm Autocannon (Pristine)": "40mm Shell",
    "80mm Naval Cannon (Pristine)": "80mm Shell",
    "70mm Shotgun Cannon (Pristine)": "70mm Shell",
}

PRISTINE_SHORT_LABEL = {
    "40mm Autocannon (Pristine)": "40mm Autocannon",
    "80mm Naval Cannon (Pristine)": "80mm Naval Cannon",
    "70mm Shotgun Cannon (Pristine)": "70mm Shotgun Cannon",
}


def _canonical_ingredient(name: str) -> str:
    key = _normalize(name)
    return INGREDIENT_ALIASES.get(key, name.strip())


def _parse_recipe_text(text: str) -> list[dict]:
    """Parse '4 Weapon Parts + 4 Metal Rods' or 'Sniper + 5 Rods OR Silenced + 2 Lenses'."""
    if re.search(r"\s+or\s+", text, re.I):
        branch = re.split(r"\s+or\s+", text, maxsplit=1, flags=re.I)[0].strip()
        return _parse_recipe_text(branch)
    inputs: list[dict] = []
    for chunk in text.replace("—", "").split("+"):
        chunk = chunk.strip()
        if not chunk:
            continue
        qty = 1
        name = chunk
        tokens = chunk.split()
        if tokens and tokens[0].isdigit():
            qty = int(tokens[0])
            name = " ".join(tokens[1:]).strip()
        name = re.sub(r"\(.*?\)", "", name).strip()
        name = _canonical_ingredient(name)
        if name:
            inputs.append({"item": name, "qty": qty})
    return inputs


def where_to_obtain(item_name: str, knowledge: dict) -> str:
    target = _normalize(item_name)
    for item in knowledge.get("items", []):
        if _normalize(item.get("name", "")) == target:
            return item.get("where_to_obtain") or item.get("action_plan") or "Weapon Crates / world loot"
    defaults = {
        "scrap metal": "Any workbench craft · towns",
        "metal rods": "Weapon Crates · towns · forts",
        "weapon parts": "Weapon Crates · dismantle weapons",
        "optic lenses": "Weapon Crates · rare drops",
        "fabric": "Towns · general loot",
        "gunpowder": "Towns · military loot",
        "petros": "Weapon Crates",
        "1874 petros": "Weapon Crates",
        "sniper": "Craft @ Fort bench",
        "silenced": "Craft @ Fort bench",
    }
    for key, val in defaults.items():
        if key in target:
            return val
    return "Weapon Crates · towns · forts"


def build_craft_chain(output_name: str, knowledge: dict, depth: int = 0, max_depth: int = 6) -> list[dict]:
    """Multi-step craft chain: base → mod → final."""
    if depth >= max_depth:
        return []

    recipe = _find_recipe_for(output_name, knowledge)
    if not recipe or not recipe.get("inputs"):
        return [{
            "step": depth + 1,
            "output": output_name,
            "workbench": None,
            "action": f"Obtain **{output_name}** — {where_to_obtain(output_name, knowledge)}",
            "inputs": [],
        }]

    chain: list[dict] = []
    for inp in recipe["inputs"]:
        sub = build_craft_chain(inp["item"], knowledge, depth + 1, max_depth)
        chain.extend(sub)

    input_summary = ", ".join(
        f"{inp['qty']}× {inp['item']}" for inp in recipe["inputs"]
    )
    chain.append({
        "step": len(chain) + 1,
        "output": output_name,
        "workbench": recipe.get("workbench", "Workbench"),
        "action": (
            f"Craft **{output_name}** @ {recipe.get('workbench', 'Workbench')} "
            f"({input_summary})"
        ),
        "inputs": recipe["inputs"],
    })
    return chain


def aggregate_craft_materials(
    output_name: str,
    knowledge: dict,
    multiplier: int = 1,
    depth: int = 0,
    max_depth: int = 6,
) -> dict[str, int]:
    """Sum leaf materials for a full craft tree (base mats only)."""
    if depth >= max_depth:
        return {_canonical_ingredient(output_name): multiplier}

    recipe = _find_recipe_for(output_name, knowledge)
    if not recipe or not recipe.get("inputs"):
        return {_canonical_ingredient(output_name): multiplier}

    totals: dict[str, int] = defaultdict(int)
    for inp in recipe["inputs"]:
        sub = aggregate_craft_materials(
            inp["item"],
            knowledge,
            multiplier * inp["qty"],
            depth + 1,
            max_depth,
        )
        for name, qty in sub.items():
            totals[name] += qty
    return dict(totals)


def list_pristine_variants(knowledge: dict) -> list[dict]:
    """Every item marked Pristine tier in the knowledge base."""
    rows: list[dict] = []
    seen: set[str] = set()
    for item in knowledge.get("items", []):
        tier = item.get("tier") or item.get("rarity") or ""
        if tier != "Pristine":
            continue
        name = item.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append(item)
    rows.sort(key=lambda i: i.get("name", ""))
    return rows


def _is_pristine_list_query(query: str) -> bool:
    q = _normalize(query)
    return q in (
        "pristine",
        "pristine turrets",
        "pristine cannons",
        "pristine turret",
        "pristine variants",
    )


def resolve_pristine_query(query: str, knowledge: dict) -> dict | None:
    """Match pristine 40mm / 80m / 70mm etc. to a single Pristine turret item."""
    q = _normalize(query)
    q = re.sub(r"\b(40|80|70)\s*m\b", r"\1mm", q)
    if "pristine" not in q and not re.search(r"\b(40|80|70)\s*m\b", q):
        return None

    rules: list[tuple[tuple[str, ...], str]] = [
        (("40", "autocannon"), "40mm Autocannon (Pristine)"),
        (("80", "naval"), "80mm Naval Cannon (Pristine)"),
        (("70", "shotgun"), "70mm Shotgun Cannon (Pristine)"),
        (("40",), "40mm Autocannon (Pristine)"),
        (("80",), "80mm Naval Cannon (Pristine)"),
        (("70",), "70mm Shotgun Cannon (Pristine)"),
    ]
    for keys, target_name in rules:
        if all(k in q for k in keys):
            for item in list_pristine_variants(knowledge):
                if item.get("name") == target_name:
                    return item

    if "pristine" in q:
        resolved = resolve_item(query, knowledge, min_score=65)
        if resolved:
            name = resolved["matched_name"]
            if "(Pristine)" in name or (resolved.get("record") or {}).get("tier") == "Pristine":
                for item in list_pristine_variants(knowledge):
                    if _normalize(item.get("name", "")) == _normalize(name):
                        return item
    return None


def format_materials_clean(rows: list[dict]) -> str:
    """One material per line — `Qty× Item`."""
    if not rows:
        return "*Loot from Weapon Crates — no craft recipe.*"
    return "\n".join(f"`{row.get('qty', 1)}× {row['item']}`" for row in rows)


def _material_rows_for_item(name: str, knowledge: dict) -> list[dict]:
    recipe = _find_recipe_for(name, knowledge)
    if recipe and recipe.get("inputs"):
        if recipe.get("source") == "in_game_ui":
            return [{"item": inp["item"], "qty": inp["qty"]} for inp in recipe["inputs"]]
        totals = aggregate_craft_materials(name, knowledge)
        return [{"item": mat, "qty": qty} for mat, qty in sorted(totals.items())]
    return []


def format_pristine_single(item: dict, knowledge: dict) -> dict[str, Any]:
    name = item.get("name", "Pristine turret")
    short = PRISTINE_SHORT_LABEL.get(name, name.replace(" (Pristine)", ""))
    obtain = item.get("where_to_obtain", "Rare+ Weapon Crates · Forts")
    recipe = _find_recipe_for(name, knowledge)
    material_rows = _material_rows_for_item(name, knowledge)

    if recipe and recipe.get("inputs"):
        wb = recipe.get("workbench", "S&H Armaments Workshop")
        subtitle = f"Upgrade @ **{wb}** · requires matching **Worn** turret"
        materials_label = "Materials"
    else:
        subtitle = f"**Obtain:** {obtain}"
        materials_label = "Materials"

    return {
        "ok": True,
        "layout": "clean",
        "title": f"Pristine {short}",
        "subtitle": subtitle,
        "material_rows": material_rows,
        "materials_label": materials_label,
        "matched_item": name,
        "intent": "pristine_single",
        "intent_label": "Pristine turret",
        "craft_chain": [],
        "steps": [],
        "summary": "",
    }


def format_pristine_answer(knowledge: dict) -> dict[str, Any]:
    variants = list_pristine_variants(knowledge)
    cards: list[dict] = []
    for item in variants:
        name = item.get("name", "")
        cards.append({
            "title": PRISTINE_SHORT_LABEL.get(name, name),
            "obtain": "S&H Armaments Workshop upgrade"
            if _find_recipe_for(name, knowledge)
            else item.get("where_to_obtain", "Rare+ Weapon Crates"),
            "material_rows": _material_rows_for_item(name, knowledge),
        })

    return {
        "ok": True,
        "layout": "pristine_hub",
        "title": "Pristine turrets",
        "subtitle": "Search a specific turret: `/sand craft pristine 40mm` · `/sand craft pristine 80mm` · `/sand craft pristine 70mm`",
        "pristine_cards": cards,
        "matched_item": None,
        "intent": "pristine_list",
        "intent_label": "Pristine variants",
        "material_rows": [],
        "craft_chain": [],
        "steps": [],
        "summary": "",
    }


def aggregate_materials(rows: list[dict]) -> dict[str, int]:
    totals: dict[str, int] = defaultdict(int)
    for row in rows:
        totals[row["item"]] += row["qty"]
    return dict(totals)


def _pristine_turret_steps(knowledge: dict, query: str) -> list[str]:
    q = _normalize(query)
    weapons: list[str] = []
    for key, label in [
        ("40mm", "40mm Autocannon"),
        ("80mm", "80mm Naval Cannon"),
        ("70mm", "70mm Shotgun Cannon"),
        ("autocannon", "40mm Autocannon"),
        ("naval", "80mm Naval Cannon"),
        ("shotgun", "70mm Shotgun Cannon"),
    ]:
        if key in q:
            weapons = [label]
            break
    if not weapons:
        weapons = ["40mm Autocannon", "80mm Naval Cannon", "70mm Shotgun Cannon"]

    steps = [
        "Stock **Time Bombs** (2 Fabric + 2 Gunpowder @ Fort bench) and ammo crates before deploying.",
        "Queue **Voyage** → target a Fort (**Istria**, **Metternich**, **Arpad**, or **Tarndpol**). Scout mine lanes on foot first.",
        "Breach **double red doors** with Time Bombs, grenades, barrels, or 80mm shells.",
        "Clear the armory and loot **Weapons Crates** (gold = Very Rare tier).",
    ]
    for w in weapons:
        tier_rows = [
            t for t in knowledge.get("turret_tiers", [])
            if w.lower() in _normalize(t.get("weapon", "")) and t.get("tier") == "Pristine"
        ]
        obtain = tier_rows[0].get("where_to_obtain") if tier_rows else "Rare+ Weapon Crates · Forts"
        steps.append(f"Extract **Pristine {w}** ({obtain}) and store in hangar.")
    steps.append("Mount on Trampler. **Pristine** tier gap vs Rusty is huge — upgrade before PvP.")
    return steps


def _fort_steps() -> list[str]:
    return [
        "Craft **2+ Time Bombs** (2 Fabric + 2 Gunpowder each) at a Fort workbench.",
        "Approach on foot — mark safe lanes through **minefields**.",
        "Breach outer **red door**, then inner red door (explosives or 80mm).",
        "Clear armory → loot **Weapons Crates** + **Crate of Shells**.",
        "Extract at nearest tower; install turrets on Trampler immediately.",
    ]


def _storm_dive_steps() -> list[str]:
    return [
        "Load **Pristine 40mm + 80mm**, full ammo, **Armored Jacket**, medkits.",
        "Deploy **Storm Dive** — fast early-town loot, watch sandstorm timer.",
        "Rush **Final Extract** at map center when it spawns.",
        "Fight PvP/PvE into **Dreadnaught** interior.",
        "Loot **Experimental** turrets, **Anti-Reactor Rifle**, **Orbital Strike Pointer**.",
        "Extract before zone closes — Experimental is Dreadnaught-exclusive.",
    ]


def _acquisition_steps_for(query: str, knowledge: dict) -> list[str]:
    q = _normalize(query)
    plans = knowledge.get("acquisition_plans", [])
    matched = []
    for plan in plans:
        blob = _normalize(
            f"{plan.get('goal', '')} {plan.get('target_location', '')} {plan.get('loadout_needed', '')}"
        )
        if any(tok in blob for tok in q.split() if len(tok) > 3):
            matched.append(plan)
    if not matched:
        matched = plans[:5]
    return [
        f"**{plan.get('goal', '')}** — {plan.get('mode', '')} @ {plan.get('target_location', '')} "
        f"(need: {plan.get('loadout_needed', '')})"
        for plan in matched[:6]
    ]


def format_materials_answer(item_name: str, knowledge: dict) -> dict[str, Any]:
    resolved = resolve_item(item_name, knowledge)
    if not resolved:
        suggestions = suggest_closest_matches(item_name, knowledge)
        return {
            "ok": False,
            "title": "Item not found",
            "subtitle": f"No match for **{item_name}**.",
            "suggestions": suggestions,
            "steps": [],
            "material_rows": [],
            "craft_chain": [],
            "summary": "",
        }

    display_name = resolved["matched_name"]
    recipe = _find_recipe_for(display_name, knowledge)
    craft_chain = build_craft_chain(display_name, knowledge)

    material_rows: list[dict] = []
    if recipe and recipe.get("inputs"):
        for inp in recipe["inputs"]:
            material_rows.append({
                "item": inp["item"],
                "qty": inp["qty"],
                "where": where_to_obtain(inp["item"], knowledge),
            })
        totals = aggregate_materials(material_rows)
        summary = " · ".join(f"**{qty}×** {name}" for name, qty in sorted(totals.items()))
        workbench = recipe.get("workbench", "Workbench")
    elif recipe and recipe.get("craft_recipe_text"):
        workbench = recipe.get("workbench", "Workbench")
        summary = recipe["craft_recipe_text"]
        material_rows = []
    else:
        item = resolved["record"] if resolved["kind"] == "item" else {}
        obtain = item.get("where_to_obtain", "Weapon Crates / world loot")
        return {
            "ok": True,
            "title": f"Materials — {display_name}",
            "subtitle": f"No craft recipe — obtain via loot.",
            "workbench": None,
            "material_rows": [{"item": display_name, "qty": 1, "where": obtain}],
            "craft_chain": [],
            "summary": f"Loot / buy: **{obtain}**",
            "steps": [f"**Obtain:** {obtain}", item.get("action_plan", "")] if item.get("action_plan") else [f"**Obtain:** {obtain}"],
            "matched_item": display_name,
            "intent": "material_cost",
        }

    chain_steps = [c["action"] for c in craft_chain if c.get("action")]

    return {
        "ok": True,
        "title": f"Materials — {display_name}",
        "subtitle": f"Craft @ **{workbench}**",
        "workbench": workbench,
        "material_rows": material_rows,
        "craft_chain": chain_steps,
        "summary": summary,
        "steps": chain_steps or [summary],
        "matched_item": display_name,
        "intent": "material_cost",
    }


def format_craft_answer(item_query: str, knowledge: dict) -> dict[str, Any]:
    """Craft-focused answer with clean material lists."""
    pristine_item = resolve_pristine_query(item_query, knowledge)
    if pristine_item:
        return format_pristine_single(pristine_item, knowledge)
    if _is_pristine_list_query(item_query):
        return format_pristine_answer(knowledge)

    resolved = resolve_item(item_query, knowledge)
    if not resolved:
        suggestions = suggest_closest_matches(item_query, knowledge)
        return {
            "ok": False,
            "title": "Item not found",
            "subtitle": f"No craft match for **{item_query}**.",
            "suggestions": suggestions,
            "steps": [],
            "material_rows": [],
            "craft_chain": [],
            "summary": "",
        }

    display_name = resolved["matched_name"]
    item = resolved["record"] if resolved["kind"] == "item" else {}

    recipe = _find_recipe_for(display_name, knowledge)
    craft_chain = build_craft_chain(display_name, knowledge)

    if not recipe or (not recipe.get("inputs") and not recipe.get("craft_recipe_text")):
        obtain = item.get("where_to_obtain", "Weapon Crates / world loot")
        return {
            "ok": True,
            "layout": "clean",
            "title": display_name,
            "subtitle": f"**Obtain:** {obtain}",
            "workbench": None,
            "material_rows": [],
            "craft_chain": [],
            "summary": "",
            "steps": [],
            "matched_item": display_name,
            "intent": "craft_item",
            "intent_label": "Crafting",
        }

    workbench = recipe.get("workbench", "Workbench")
    totals = aggregate_craft_materials(display_name, knowledge)
    material_rows = [{"item": name, "qty": qty} for name, qty in sorted(totals.items())]

    return {
        "ok": True,
        "layout": "clean",
        "title": display_name,
        "subtitle": f"@ **{workbench}**",
        "workbench": workbench,
        "material_rows": material_rows,
        "craft_chain": [c["action"] for c in craft_chain if c.get("action")],
        "summary": "",
        "steps": [],
        "matched_item": display_name,
        "intent": "craft_item",
        "intent_label": "Crafting",
    }


def format_query_answer(query: str, knowledge: dict) -> dict[str, Any]:
    intent = detect_intent(query, knowledge)
    resolved = resolve_item(query, knowledge)
    item_name = resolved["matched_name"] if resolved else None

    steps: list[str] = []
    title = "SAND Guide"
    subtitle = ""

    if intent == "get_pristine_turret" or (
        "pristine" in _normalize(query) and any(w in _normalize(query) for w in ("cannon", "turret", "40mm", "80mm"))
    ):
        title = "How to get Pristine turrets"
        subtitle = "Fort raids → Very Rare crates → hangar install"
        steps = _pristine_turret_steps(knowledge, query)

    elif intent == "material_cost":
        item_q = query
        for prefix in ("materials for", "material for", "how many", "cost for", "recipe for"):
            if prefix in _normalize(query):
                item_q = _normalize(query).split(prefix, 1)[-1].strip() or query
                break
        result = format_materials_answer(item_q if item_q != query else (item_name or query), knowledge)
        result["intent"] = intent
        return result

    elif intent == "craft_item" and item_name:
        chain = build_craft_chain(item_name, knowledge)
        title = f"How to craft {item_name}"
        subtitle = f"Intent: {INTENT_LABELS.get(intent, intent)}"
        if chain:
            steps = [c["action"] for c in chain]
        else:
            item = resolved["record"] if resolved else {}
            steps = [f"**Obtain:** {item.get('where_to_obtain', 'Weapon Crates')}"]
            if item.get("action_plan"):
                steps.append(item["action_plan"])

    elif intent == "where_to_loot" and item_name:
        item = resolved["record"] if resolved else {}
        title = f"Where to get {item_name}"
        subtitle = "Best loot sources"
        steps = [
            f"Primary source: **{item.get('where_to_obtain', 'Weapon Crates · Forts · Storm Dive')}**",
        ]
        if item.get("action_plan"):
            steps.append(item["action_plan"])

    elif intent == "fort_raid":
        title = "Fort raid protocol"
        subtitle = "Time Bombs → red doors → armory crates"
        steps = _fort_steps()

    elif intent == "storm_dive":
        title = "Storm Dive → Dreadnaught"
        subtitle = "Endgame Experimental loot"
        steps = _storm_dive_steps()

    elif item_name:
        item = resolved["record"] if resolved else {}
        title = item_name
        subtitle = INTENT_LABELS.get(intent, "Item lookup")
        if item.get("where_to_obtain"):
            steps.append(f"**Obtain:** {item['where_to_obtain']}")
        if item.get("craft_recipe_text"):
            steps.append(f"**Craft:** {item['craft_recipe_text']}")
        if item.get("action_plan"):
            steps.append(f"**Plan:** {item['action_plan']}")
        recipe = _find_recipe_for(item_name, knowledge)
        if recipe and recipe.get("inputs"):
            mats = ", ".join(f"{i['qty']}× {i['item']}" for i in recipe["inputs"])
            steps.append(f"**Materials:** {mats} @ {recipe.get('workbench', 'Workbench')}")

    if not steps:
        suggestions = suggest_closest_matches(query, knowledge)
        if suggestions:
            title = "No exact match"
            subtitle = "Try one of these items or rephrase your question:"
            steps = [f"**{name}** ({score}% match)" for name, score in suggestions]
            steps.extend(_acquisition_steps_for(query, knowledge)[:3])
        else:
            title = "SAND acquisition plan"
            subtitle = "General progression from the ShadowSyn guide"
            steps = _acquisition_steps_for(query, knowledge)

    return {
        "ok": True,
        "title": title,
        "subtitle": subtitle,
        "steps": steps,
        "intent": intent,
        "intent_label": INTENT_LABELS.get(intent, intent),
        "matched_item": item_name,
        "material_rows": [],
        "craft_chain": [],
        "summary": "",
    }


def truncate_for_discord(text: str, limit: int = 1024) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 15] + "… _(more)_"


def format_materials_table(rows: list[dict]) -> str:
    if not rows:
        return "_No parsed materials — see craft chain below._"
    lines = ["Item | Qty | Where to get", "---|---:|---"]
    for row in rows:
        item = row["item"][:28]
        lines.append(f"{item} | {row['qty']} | {row['where'][:40]}")
    return "\n".join(lines)
