"""Scrape sandgame.wiki crafting/material data into Shadow/data/sand_knowledge.json."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
_SAND_REPO = Path(r"C:\Users\josep\Desktop\Joe\Cursor\sand-raiders-of-sophie\scripts")
if _SAND_REPO.exists():
    sys.path.insert(0, str(_SAND_REPO))

try:
    from sand_hardcoded_data import build_hardcoded_knowledge
except ImportError:
    build_hardcoded_knowledge = None  # type: ignore

from cogs.sand.pristine_data import merge_pristine_into_knowledge

OUTPUT = ROOT / "data" / "sand_knowledge.json"
WIKI_API = "https://sandgame.wiki/api.php"
USER_AGENT = "ShadowSyn-SAND-Scraper/1.0"

PRIORITY_CATEGORIES = [
    "Category:Player_Weapons",
    "Category:Mounted_Weapons",
    "Category:Crafting_Components",
    "Category:Materials_and_Components",
    "Category:Ammunition",
    "Category:Landmarks",
    "Category:Forts",
    "Category:Towns",
    "Category:Items",
    "Category:Special_Weapons",
    "Category:Rifles",
    "Category:Shotguns",
    "Category:Handguns",
]

PRIORITY_PAGES = [
    "Crafting",
    "Time Bomb",
    "Weapon Crate",
    "Weapons Crate",
    "Loot Containers",
    "Storm Dive",
    "Dreadnaught",
    "Fabric",
    "Gunpowder",
    "High-Grade Gunpowder",
    "Weapon Parts",
    "Metal Rods",
    "Scrap Metal",
    "Optic Lenses",
    "Threads",
    "Fabric Scraps",
    "Scrapped Ammo",
    "Spare Parts",
    "Mechanical Components",
    "S&H Compact Armaments Workshop",
    "S&H Armaments Workshop",
]

ICON_RE = re.compile(
    r"(\d+)x\s*\{\{Icon\|[^|]*\|3=([^}|]+)",
    re.IGNORECASE,
)
ICON_SIMPLE_RE = re.compile(
    r"(\d+)x\s*\{\{Icon\|([^|}\s]+)",
    re.IGNORECASE,
)
WIKITABLE_RE = re.compile(r"\{\| class=\"wikitable[^\"]*\".*?\|\}", re.DOTALL | re.IGNORECASE)
WEAPONS_TEMPLATE_RE = re.compile(r"\{\{Weapons\s*\n(.*?)\n\}\}", re.DOTALL | re.IGNORECASE)
TEMPLATE_FIELD_RE = re.compile(r"\|\s*(\w+)\s*=\s*(.+)", re.IGNORECASE)
TIER_HEADER_RE = re.compile(r"====\s*Tier\s*(\d+)\s*-\s*(\w+)\s*====", re.IGNORECASE)
CATEGORY_RE = re.compile(r"\[\[Category:([^\]]+)\]\]", re.IGNORECASE)
REDIRECT_RE = re.compile(r"#REDIRECT\s*\[\[([^\]]+)\]\]", re.IGNORECASE)
ROW_SPLIT_RE = re.compile(r"^\|-", re.MULTILINE)
DATA_ROW_RE = re.compile(
    r"\n\|[^\n!].*?(?=\n\|-|\n\|\})",
    re.DOTALL,
)
WORKBENCH_RE = re.compile(r"\|\s*([^|\n]*(?:Workbench|Workshop)[^|\n]*)", re.IGNORECASE)
ICON_NAME_RE = re.compile(
    r"(\d+)x\s*\{\{Icon\|(?:[^|}|]+\|3=)?([^}|]+)",
    re.IGNORECASE,
)


def _api(params: dict) -> dict:
    query = urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(
        f"{WIKI_API}?{query}",
        headers={"User-Agent": USER_AGENT},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"]))
    return payload


def _clean_wiki_text(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\[\[([^|\]]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    return text.strip()


def _normalize_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


NAME_ALIASES = {
    "1874e petros rifle": "1874 Petros",
    "1874 petros rifle": "1874 Petros",
    "1874s petros sniper rifle": "1874 Petros Sniper",
    "1874e/sd petros rifle (silenced)": "1874 Petros Silenced",
    "1874s/sd petros sniper rifle (silenced)": "1874 Petros Sniper Silenced",
    "blitz pps-5 pistol": "Blitz Pistol PPS-5",
    "blitz 10r pistol": "Blitz Pistol 10R",
    "eb zseb revolver": "EB Revolver Zseb",
    "eb bantam revolver": "EB Revolver Bantam",
    "pepper mill shotgun": "Pepper Mill",
    "drobulet shotgun": "Drobulet",
    "drobulet shotgun (vertical choke)": "Drobulet Vertical Choke",
    "m1866/9 einzel breechloader": "866/9 Rifle Einzel",
    "kf866/9r mehrzel repeater": "866/9 Rifle Mehrzel",
    "40mm autocannon (pristine)": "40mm Autocannon (Pristine)",
    "80mm naval cannon (pristine)": "80mm Naval Cannon (Pristine)",
    "70mm shotgun cannon (pristine)": "70mm Shotgun Cannon (Pristine)",
    "40mm autocannon (worn)": "40mm Autocannon (Worn)",
    "80mm naval cannon (worn)": "80mm Naval Cannon (Worn)",
    "70mm shotgun cannon (worn)": "70mm Shotgun Cannon (Worn)",
}


def _canonical_name(name: str) -> str:
    clean = _clean_wiki_text(name)
    return NAME_ALIASES.get(_normalize_key(clean), clean)


def _parse_icons(cell: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for qty_raw, item_name in ICON_NAME_RE.findall(cell):
        qty = int(qty_raw) if qty_raw.isdigit() else 1
        name = _canonical_name(item_name.strip())
        if name.lower() not in ("right", "left"):
            found.append((qty, name))
    if not found:
        for qty_raw, item_name in ICON_RE.findall(cell):
            qty = int(qty_raw) if qty_raw.isdigit() else 1
            found.append((qty, _canonical_name(item_name)))
    return found


def _parse_craft_tables(wikitext: str, page: str) -> list[dict]:
    """Parse all wikitable craft blocks (Crafted from / Used to craft)."""
    recipes: list[dict] = []
    for table in WIKITABLE_RE.findall(wikitext):
        if "{{Icon" not in table:
            continue
        header_blob = table[:500].lower()
        if not any(k in header_blob for k in ("crafted from", "used to craft", "recipe ingredients")):
            continue

        for row in DATA_ROW_RE.findall(table):
            if "{{Icon" not in row:
                continue
            icons = _parse_icons(row)
            if len(icons) < 2:
                continue

            output = icons[0][1]
            inputs = [{"item": name, "qty": qty} for qty, name in icons[1:]]
            wb_match = WORKBENCH_RE.search(row)
            workbench = _clean_wiki_text(wb_match.group(1)) if wb_match else "Workbench"

            recipes.append({
                "output": output,
                "workbench": workbench,
                "inputs": inputs,
                "source": "sandgame.wiki",
                "page": page,
            })
    return recipes


def fetch_category_members(category: str) -> list[str]:
    titles: list[str] = []
    cont: str | None = None
    while True:
        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
        }
        if cont:
            params["cmcontinue"] = cont
        data = _api(params)
        titles.extend(m["title"] for m in data.get("query", {}).get("categorymembers", []))
        cont = data.get("continue", {}).get("cmcontinue")
        if not cont:
            break
        time.sleep(0.1)
    return titles


def fetch_titles(full: bool) -> list[str]:
    if full:
        titles: list[str] = []
        cont = None
        while True:
            params = {"action": "query", "list": "allpages", "aplimit": "500"}
            if cont:
                params["apcontinue"] = cont
            data = _api(params)
            titles.extend(p["title"] for p in data["query"]["allpages"])
            cont = data.get("continue", {}).get("apcontinue")
            if not cont:
                break
            time.sleep(0.15)
        return titles

    seen: set[str] = set()
    titles = []
    for cat in PRIORITY_CATEGORIES:
        try:
            for t in fetch_category_members(cat):
                if t not in seen:
                    seen.add(t)
                    titles.append(t)
        except Exception as exc:
            print(f"  category skip {cat}: {exc}")
    for t in PRIORITY_PAGES:
        if t not in seen:
            seen.add(t)
            titles.append(t)
    return titles


def fetch_wikitext(title: str) -> str | None:
    data = _api({"action": "parse", "page": title, "prop": "wikitext"})
    if "error" in data:
        return None
    return data.get("parse", {}).get("wikitext", {}).get("*")


def _parse_weapons_templates(wikitext: str, page: str) -> list[dict]:
    items = []
    for block in WEAPONS_TEMPLATE_RE.findall(wikitext):
        fields = {}
        for line in block.splitlines():
            m = TEMPLATE_FIELD_RE.match(line.strip())
            if m:
                fields[m.group(1).lower()] = _clean_wiki_text(m.group(2))
        if fields.get("name"):
            items.append({
                "name": _canonical_name(fields["name"].strip("'\"")),
                "rarity": fields.get("rarity"),
                "type": fields.get("type"),
                "mag": fields.get("mag"),
                "damage": fields.get("damage"),
                "ammo": fields.get("ammo"),
                "value": fields.get("value"),
                "source": "sandgame.wiki",
                "page": page,
                "category": "player_weapon",
            })
    return items


def _parse_turret_tiers(page_title: str, wikitext: str) -> list[dict]:
    tiers = []
    for m in TIER_HEADER_RE.finditer(wikitext):
        tiers.append({
            "weapon": page_title,
            "tier": m.group(2),
            "tier_number": int(m.group(1)),
            "source": "sandgame.wiki",
        })
    return tiers


def scrape_wiki(full: bool = False) -> dict:
    titles = fetch_titles(full)
    print(f"Scraping {len(titles)} wiki pages ({'full' if full else 'priority'})")

    items: list[dict] = []
    recipes: list[dict] = []
    turret_tiers: list[dict] = []
    landmarks: list[dict] = []
    pages_scraped = 0

    for idx, title in enumerate(titles, 1):
        if idx % 20 == 0:
            print(f"  {idx}/{len(titles)}: {title}")
        try:
            wikitext = fetch_wikitext(title)
        except Exception as exc:
            print(f"  skip {title}: {exc}")
            continue
        if not wikitext or REDIRECT_RE.search(wikitext):
            continue

        pages_scraped += 1
        items.extend(_parse_weapons_templates(wikitext, title))
        recipes.extend(_parse_craft_tables(wikitext, title))
        turret_tiers.extend(_parse_turret_tiers(title, wikitext))

        if title.startswith("Fort ") or "Category:Landmarks" in wikitext:
            landmarks.append({
                "name": title,
                "type": "Fort" if title.startswith("Fort ") else "Landmark",
                "wiki_excerpt": _clean_wiki_text(wikitext[:400]),
                "source": "sandgame.wiki",
            })

        time.sleep(0.04)

    return {
        "pages_total": len(titles),
        "pages_scraped": pages_scraped,
        "items": items,
        "recipes": recipes,
        "landmarks": landmarks,
        "turret_tiers": turret_tiers,
    }


def _merge_items(base: list[dict], extra: list[dict]) -> list[dict]:
    index = {_normalize_key(i.get("name", "")): i for i in base if i.get("name")}
    for item in extra:
        key = _normalize_key(item.get("name", ""))
        if not key:
            continue
        if key in index:
            index[key] = {**index[key], **{k: v for k, v in item.items() if v is not None and v != ""}}
        else:
            index[key] = item
    return list(index.values())


def _recipe_key(recipe: dict) -> tuple:
    return (
        _normalize_key(recipe.get("output", "")),
        tuple((i["item"], i["qty"]) for i in recipe.get("inputs", [])),
    )


def _merge_recipes(base: list[dict], extra: list[dict]) -> list[dict]:
    seen: set[tuple] = set()
    out: list[dict] = []
    for recipe in base + extra:
        key = _recipe_key(recipe)
        if key in seen:
            continue
        seen.add(key)
        out.append(recipe)
    return out


def _apply_recipes_to_items(items: list[dict], recipes: list[dict]) -> None:
    """Sync craft_recipe_text on items from structured recipes."""
    by_output = {_normalize_key(r["output"]): r for r in recipes}
    for item in items:
        key = _normalize_key(item.get("name", ""))
        recipe = by_output.get(key)
        if not recipe:
            continue
        mats = " + ".join(f"{i['qty']} {i['item']}" for i in recipe["inputs"])
        item["craft_recipe_text"] = mats
        item["craft_workbench"] = recipe.get("workbench")


def _atomic_write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def merge_knowledge(wiki_data: dict, hardcoded: dict | None) -> dict:
    hardcoded = hardcoded or {"items": [], "recipes": [], "landmarks": [], "acquisition_plans": [], "faq_intents": [], "item_aliases": {}, "turret_tiers": []}
    items = _merge_items(hardcoded.get("items", []), wiki_data.get("items", []))
    recipes = _merge_recipes(hardcoded.get("recipes", []), wiki_data.get("recipes", []))
    _apply_recipes_to_items(items, recipes)

    return {
        "meta": {
            "version": 2,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "sources": ["sandgame.wiki", "build_sand_guide.py"],
            "pages_total": wiki_data.get("pages_total", 0),
            "pages_scraped": wiki_data.get("pages_scraped", 0),
            "recipe_count": len(recipes),
        },
        "items": items,
        "recipes": recipes,
        "landmarks": _merge_items(
            [{"name": l["name"], **{k: v for k, v in l.items() if k != "name"}} for l in hardcoded.get("landmarks", [])],
            wiki_data.get("landmarks", []),
        ),
        "acquisition_plans": hardcoded.get("acquisition_plans", []),
        "faq_intents": hardcoded.get("faq_intents", []),
        "item_aliases": hardcoded.get("item_aliases", {}),
        "turret_tiers": _merge_items(
            hardcoded.get("turret_tiers", []),
            wiki_data.get("turret_tiers", []),
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="Scrape all wiki pages (slow)")
    args = parser.parse_args()

    wiki_data = scrape_wiki(full=args.full)
    hardcoded = build_hardcoded_knowledge() if build_hardcoded_knowledge else None
    knowledge = merge_knowledge(wiki_data, hardcoded)
    knowledge = merge_pristine_into_knowledge(knowledge)

    _atomic_write(OUTPUT, knowledge)
    print(f"Saved {OUTPUT}")
    print(
        f"  items={len(knowledge['items'])} recipes={len(knowledge['recipes'])} "
        f"pages_scraped={knowledge['meta']['pages_scraped']}"
    )
    pristine = [r for r in knowledge["recipes"] if "pristine" in r.get("output", "").lower()]
    print(f"  pristine recipes={len(pristine)}")
    for r in pristine:
        mats = ", ".join(f"{i['qty']}× {i['item']}" for i in r["inputs"])
        print(f"    {r['output']}: {mats} @ {r.get('workbench')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
