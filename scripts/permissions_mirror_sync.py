"""Mirror ShadowMain channel permission overwrites onto ShadowBackup (ShadowAdmin).

Maps roles by name and keeps member overwrites when the user is in Backup.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.guild_registry import (  # noqa: E402
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    normalize_channel_name,
)

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

OUT_DIR = Path(r"C:\Users\josep\Desktop\Joe\Cursor\discord-bots\data")

# Main category name fragments -> Backup category name fragments
CATEGORY_ALIASES: dict[str, tuple[str, ...]] = {
    "archive": ("archive", "game chat archive", "𝙖𝙧𝙘𝙝𝙞𝙫𝙚"),
}


def category_match_keys(name: str) -> set[str]:
    raw = (name or "").lower()
    norm = normalize_channel_name(name)
    keys = {raw, norm} if norm else {raw}
    for alias_group in CATEGORY_ALIASES.values():
        if any(a in raw or a in norm for a in alias_group):
            keys.update(alias_group)
    if "archive" in raw or "archive" in norm:
        keys.update(CATEGORY_ALIASES["archive"])
    return {k for k in keys if k}


def categories_match(main_name: str, backup_name: str) -> bool:
    mk = category_match_keys(main_name)
    bk = category_match_keys(backup_name)
    return bool(mk & bk)


async def fetch_json(session: aiohttp.ClientSession, method: str, url: str, payload=None):
    kwargs = {"headers": HEADERS}
    if payload is not None:
        kwargs["json"] = payload
    async with session.request(method, url, **kwargs) as resp:
        text = await resp.text()
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            data = {"raw": text}
        return resp.status, data


def role_name_map(roles: list[dict]) -> dict[str, str]:
    out: dict[str, str] = {}
    for role in roles:
        rid = role.get("id")
        name = (role.get("name") or "").lower()
        if rid and name:
            out[name] = str(rid)
    return out


def channel_keys(ch: dict) -> list[str]:
    name = ch.get("name") or ""
    keys = []
    if name:
        keys.append(name.lower())
        norm = normalize_channel_name(name)
        if norm:
            keys.append(norm)
    return keys


def build_channel_index(channels: list[dict]) -> dict[tuple[int, str], dict]:
    """Index by (type, normalized_name) — first wins; prefer exact."""
    index: dict[tuple[int, str], dict] = {}
    for ch in channels:
        for key in channel_keys(ch):
            slot = (int(ch.get("type", -1)), key)
            index.setdefault(slot, ch)
    return index


def match_backup_category(main_cat: dict, backup_cats: list[dict]) -> dict | None:
    for bc in backup_cats:
        if categories_match(main_cat.get("name") or "", bc.get("name") or ""):
            return bc
    for key in channel_keys(main_cat):
        for bc in backup_cats:
            if key in channel_keys(bc):
                return bc
    return None


def match_backup_channel(
    main_ch: dict,
    backup_channels: list[dict],
    backup_by_id: dict[str, dict],
    main_by_id: dict[str, dict],
    backup_cat_map: dict[str, str],
    backup_unique: dict[tuple[int, str], dict] | None = None,
) -> dict | None:
    main_type = int(main_ch.get("type", -1))
    main_parent = main_ch.get("parent_id")
    candidates = [c for c in backup_channels if int(c.get("type", -1)) == main_type]

    def parent_matches(backup_ch: dict) -> bool:
        mp = main_parent
        bp = backup_ch.get("parent_id")
        if not mp and not bp:
            return True
        if not mp or not bp:
            return False
        mapped = backup_cat_map.get(str(mp))
        return mapped == str(bp)

    for key in channel_keys(main_ch):
        for cand in candidates:
            if key in channel_keys(cand) and parent_matches(cand):
                return cand

    if backup_unique:
        main_type = int(main_ch.get("type", -1))
        for key in channel_keys(main_ch):
            slot = (main_type, key)
            if slot in backup_unique:
                return backup_unique[slot]
    return None


def build_unique_index(channels: list[dict]) -> dict[tuple[int, str], dict]:
    counts: dict[tuple[int, str], int] = {}
    index: dict[tuple[int, str], dict] = {}
    for ch in channels:
        t = int(ch.get("type", -1))
        for key in channel_keys(ch):
            slot = (t, key)
            counts[slot] = counts.get(slot, 0) + 1
            index[slot] = ch
    return {k: v for k, v in index.items() if counts.get(k, 0) == 1}


def translate_overwrite(
    ow: dict,
    main_guild_id: int,
    backup_guild_id: int,
    backup_roles: dict[str, str],
    backup_member_ids: set[str],
) -> dict | None:
    oid = str(ow.get("id", ""))
    otype = int(ow.get("type", 0))
    allow = str(ow.get("allow", "0"))
    deny = str(ow.get("deny", "0"))

    if otype == 0:
        if oid == str(main_guild_id):
            return {"id": str(backup_guild_id), "type": 0, "allow": allow, "deny": deny}
        # role overwrite — resolved by caller supplying main role name lookup
        return {"_main_role_id": oid, "type": 0, "allow": allow, "deny": deny}

    if otype == 1:
        if oid not in backup_member_ids:
            return None
        return {"id": oid, "type": 1, "allow": allow, "deny": deny}
    return None


def finalize_role_overwrite(partial: dict, main_role_names: dict[str, str], backup_roles: dict[str, str]) -> dict | None:
    main_rid = partial.pop("_main_role_id", None)
    if not main_rid:
        return None
    role_name = main_role_names.get(main_rid)
    if not role_name:
        return None
    backup_rid = backup_roles.get(role_name.lower())
    if not backup_rid:
        return None
    return {
        "id": backup_rid,
        "type": 0,
        "allow": partial["allow"],
        "deny": partial["deny"],
    }


def overwrites_equal(a: list[dict], b: list[dict]) -> bool:
    def norm(items):
        return sorted(
            (
                {
                    "id": str(x["id"]),
                    "type": int(x["type"]),
                    "allow": str(x["allow"]),
                    "deny": str(x["deny"]),
                }
                for x in items
            ),
            key=lambda x: (x["type"], x["id"]),
        )

    return norm(a) == norm(b)


async def member_ids_in_guild(session: aiohttp.ClientSession, guild_id: int) -> set[str]:
    ids: set[str] = set()
    after = "0"
    for _ in range(50):
        status, data = await fetch_json(
            session,
            "GET",
            f"https://discord.com/api/v10/guilds/{guild_id}/members?limit=1000&after={after}",
        )
        if status != 200 or not isinstance(data, list) or not data:
            break
        for m in data:
            uid = m.get("user", {}).get("id")
            if uid:
                ids.add(str(uid))
        after = data[-1]["user"]["id"]
        if len(data) < 1000:
            break
    return ids


async def main(apply: bool):
    async with aiohttp.ClientSession() as session:
        _, main_roles_raw = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_MAIN_GUILD_ID}/roles"
        )
        _, backup_roles_raw = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_BACKUP_GUILD_ID}/roles"
        )
        _, main_channels = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_MAIN_GUILD_ID}/channels"
        )
        _, backup_channels = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_BACKUP_GUILD_ID}/channels"
        )

        main_roles = main_roles_raw if isinstance(main_roles_raw, list) else []
        backup_roles = role_name_map(backup_roles_raw if isinstance(backup_roles_raw, list) else [])
        main_role_names = {
            str(r["id"]): (r.get("name") or "").lower()
            for r in main_roles
            if r.get("id")
        }

        main_by_id = {str(c["id"]): c for c in main_channels}
        backup_by_id = {str(c["id"]): c for c in backup_channels}

        backup_members = await member_ids_in_guild(session, SHADOW_BACKUP_GUILD_ID)

        # Map categories first
        backup_cat_map: dict[str, str] = {}
        main_cats = [c for c in main_channels if c.get("type") == 4]
        backup_cats = [c for c in backup_channels if c.get("type") == 4]
        backup_unique = build_unique_index(backup_channels)
        unmatched_cats = []
        for mc in main_cats:
            match = match_backup_category(mc, backup_cats)
            if match:
                backup_cat_map[str(mc["id"])] = str(match["id"])
            else:
                unmatched_cats.append(mc.get("name"))

        plan: list[dict] = []
        skipped: list[str] = []
        unmatched: list[str] = []

        sync_order = sorted(
            [c for c in main_channels if c.get("type") != 4],
            key=lambda c: (c.get("parent_id") is None, c.get("position", 0)),
        )

        for main_ch in sync_order:
            backup_ch = match_backup_channel(
                main_ch,
                backup_channels,
                backup_by_id,
                main_by_id,
                backup_cat_map,
                backup_unique,
            )
            if not backup_ch:
                unmatched.append(f"{main_ch.get('name')} (type {main_ch.get('type')})")
                continue

            translated: list[dict] = []
            dropped: list[str] = []
            for ow in main_ch.get("permission_overwrites") or []:
                partial = translate_overwrite(
                    ow,
                    SHADOW_MAIN_GUILD_ID,
                    SHADOW_BACKUP_GUILD_ID,
                    backup_roles,
                    backup_members,
                )
                if partial is None:
                    oid = str(ow.get("id"))
                    dropped.append(f"member:{oid}" if ow.get("type") == 1 else f"role:{oid}")
                    continue
                if "_main_role_id" in partial:
                    final = finalize_role_overwrite(partial, main_role_names, backup_roles)
                    if not final:
                        dropped.append(f"role:{ow.get('id')} (no backup role match)")
                        continue
                    translated.append(final)
                else:
                    translated.append(partial)

            current = backup_ch.get("permission_overwrites") or []
            if overwrites_equal(current, translated):
                continue

            plan.append(
                {
                    "main_id": main_ch["id"],
                    "backup_id": backup_ch["id"],
                    "name": main_ch.get("name"),
                    "type": main_ch.get("type"),
                    "dropped": dropped,
                    "before_count": len(current),
                    "after_count": len(translated),
                    "overwrites": translated,
                }
            )

        # Categories too
        for mc in main_cats:
            backup_ch = match_backup_category(mc, backup_cats)
            if not backup_ch:
                continue
            translated = []
            dropped = []
            for ow in mc.get("permission_overwrites") or []:
                partial = translate_overwrite(
                    ow,
                    SHADOW_MAIN_GUILD_ID,
                    SHADOW_BACKUP_GUILD_ID,
                    backup_roles,
                    backup_members,
                )
                if partial is None:
                    dropped.append(str(ow.get("id")))
                    continue
                if "_main_role_id" in partial:
                    final = finalize_role_overwrite(partial, main_role_names, backup_roles)
                    if not final:
                        dropped.append(str(ow.get("id")))
                        continue
                    translated.append(final)
                else:
                    translated.append(partial)
            current = backup_ch.get("permission_overwrites") or []
            if not overwrites_equal(current, translated):
                plan.append(
                    {
                        "main_id": mc["id"],
                        "backup_id": backup_ch["id"],
                        "name": mc.get("name"),
                        "type": 4,
                        "dropped": dropped,
                        "before_count": len(current),
                        "after_count": len(translated),
                        "overwrites": translated,
                    }
                )

        print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
        print(f"Channels to update: {len(plan)}")
        if unmatched_cats:
            print(f"Unmatched categories ({len(unmatched_cats)}): {', '.join(unmatched_cats)}")
        if unmatched:
            print(f"Unmatched channels on Backup ({len(unmatched)}):")
            for u in unmatched:
                print(f"  - {u}")

        applied = 0
        errors = []
        for item in plan:
            print(
                f"\n{'APPLY' if apply else 'WOULD UPDATE'} {item['name']!r} "
                f"(backup {item['backup_id']}) "
                f"overwrites {item['before_count']} -> {item['after_count']}"
            )
            if item["dropped"]:
                print(f"  dropped: {', '.join(item['dropped'])}")
            if apply:
                status, data = await fetch_json(
                    session,
                    "PATCH",
                    f"https://discord.com/api/v10/channels/{item['backup_id']}",
                    {"permission_overwrites": item["overwrites"]},
                )
                if status in (200, 201):
                    applied += 1
                    print("  OK")
                else:
                    msg = data.get("message", data)
                    errors.append(f"{item['name']}: {msg}")
                    print(f"  ERR {status}: {msg}")
                await asyncio.sleep(0.35)

        report = {
            "mode": "apply" if apply else "dry-run",
            "planned_updates": len(plan),
            "applied": applied,
            "errors": errors,
            "unmatched_channels": unmatched,
            "unmatched_categories": unmatched_cats,
            "plan_summary": [
                {
                    "name": p["name"],
                    "backup_id": p["backup_id"],
                    "before_count": p["before_count"],
                    "after_count": p["after_count"],
                    "dropped": p["dropped"],
                }
                for p in plan
            ],
        }
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        out_path = OUT_DIR / "permissions_mirror_sync_report.json"
        out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nReport: {out_path}")
        print(f"Applied: {applied}/{len(plan)}" if apply else f"Would apply: {len(plan)}")
        if errors:
            print("Errors:", len(errors))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Write changes to ShadowBackup")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
