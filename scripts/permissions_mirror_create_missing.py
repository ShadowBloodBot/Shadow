"""Create missing ShadowMain channels on ShadowBackup with mirrored permission overwrites."""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.guild_registry import SHADOW_BACKUP_GUILD_ID, SHADOW_MAIN_GUILD_ID, normalize_channel_name
from scripts.permissions_mirror_sync import (
    categories_match,
    channel_keys,
    finalize_role_overwrite,
    member_ids_in_guild,
    role_name_map,
    translate_overwrite,
)

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

MISSING_CHANNELS = ("『🌟』𝙣𝙤𝙩𝙞𝙘𝙚", "𝘽𝙡𝙤𝙤𝙙𝙡𝙚𝙩𝙩𝙞𝙣𝙜's 𝙍𝙤𝙤𝙢")

# Discord API may reject legacy type 5 creation — mirror as text (0) with same overwrites.
TYPE_FALLBACK = {5: 0}


async def fetch_json(session, method, url, payload=None):
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


def find_category(main_parent_id: str, main_cats: list[dict], backup_cats: list[dict]) -> str | None:
    main_cat = next((c for c in main_cats if str(c["id"]) == str(main_parent_id)), None)
    if not main_cat:
        return None
    for bc in backup_cats:
        if categories_match(main_cat.get("name") or "", bc.get("name") or ""):
            return str(bc["id"])
    return None


async def main():
    async with aiohttp.ClientSession() as session:
        _, main_channels = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_MAIN_GUILD_ID}/channels"
        )
        _, backup_channels = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_BACKUP_GUILD_ID}/channels"
        )
        _, main_roles_raw = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_MAIN_GUILD_ID}/roles"
        )
        _, backup_roles_raw = await fetch_json(
            session, "GET", f"https://discord.com/api/v10/guilds/{SHADOW_BACKUP_GUILD_ID}/roles"
        )

        main_role_names = {
            str(r["id"]): (r.get("name") or "").lower()
            for r in (main_roles_raw if isinstance(main_roles_raw, list) else [])
            if r.get("id")
        }
        backup_roles = role_name_map(backup_roles_raw if isinstance(backup_roles_raw, list) else [])
        backup_members = await member_ids_in_guild(session, SHADOW_BACKUP_GUILD_ID)

        main_cats = [c for c in main_channels if c.get("type") == 4]
        backup_cats = [c for c in backup_channels if c.get("type") == 4]
        backup_names = {(c.get("name") or "").lower() for c in backup_channels}

        for target_name in MISSING_CHANNELS:
            if target_name.lower() in backup_names:
                print(f"SKIP {target_name!r} — already exists on Backup")
                continue
            main_ch = next((c for c in main_channels if c.get("name") == target_name), None)
            if not main_ch:
                print(f"MISSING on Main: {target_name!r}")
                continue

            parent_id = None
            if main_ch.get("parent_id"):
                parent_id = find_category(str(main_ch["parent_id"]), main_cats, backup_cats)

            translated = []
            for ow in main_ch.get("permission_overwrites") or []:
                partial = translate_overwrite(
                    ow,
                    SHADOW_MAIN_GUILD_ID,
                    SHADOW_BACKUP_GUILD_ID,
                    backup_roles,
                    backup_members,
                )
                if partial is None:
                    continue
                if "_main_role_id" in partial:
                    final = finalize_role_overwrite(partial, main_role_names, backup_roles)
                    if final:
                        translated.append(final)
                else:
                    translated.append(partial)

            payload = {
                "name": main_ch["name"],
                "type": TYPE_FALLBACK.get(main_ch["type"], main_ch["type"]),
                "permission_overwrites": translated,
            }
            if parent_id:
                payload["parent_id"] = parent_id
            for key in ("bitrate", "user_limit", "rtc_region", "video_quality_mode"):
                if main_ch.get(key) is not None:
                    payload[key] = main_ch[key]

            status, data = await fetch_json(
                session,
                "POST",
                f"https://discord.com/api/v10/guilds/{SHADOW_BACKUP_GUILD_ID}/channels",
                payload,
            )
            if status in (200, 201):
                print(f"CREATED {target_name!r} -> {data.get('id')} under parent {parent_id}")
            else:
                print(f"FAILED {target_name!r}: {status} {data}")


if __name__ == "__main__":
    asyncio.run(main())
