"""ShadowAdmin: seed guild_registry.json by matching ShadowBackup channels/roles to ShadowMain."""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.guild_registry import (  # noqa: E402
    CHANNEL_KEYS,
    REGISTRY_PATH,
    ROLE_KEYS,
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    _SHADOW_MAIN_CHANNELS,
    _SHADOW_MAIN_ROLES,
    load_registry,
    normalize_channel_name,
    save_registry,
)

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

# Fallback slug map when unicode-styled names differ slightly
SLUG_ALIASES: dict[str, tuple[str, ...]] = {
    "lobby": ("lobby", "lɒɓɓy"),
    "clips": ("clips", "clip"),
    "casino": ("casino",),
    "steam_codes": ("steam-codes", "steam codes", "steamcodes"),
    "sand_general": ("sand-general", "sand general"),
    "war": ("quinfall-war", "war"),
    "arma_stats": ("arma-stats", "arma stats"),
    "steam_action_pvp": ("action-pvp", "action pvp"),
    "steam_adventure_coop": ("adventure-co-op", "adventure co-op"),
    "game_roles": ("game-roles", "game roles"),
}


async def fetch_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url, headers=HEADERS) as resp:
        return resp.status, await resp.json()


def build_name_index(channels: list[dict]) -> dict[str, str]:
    index: dict[str, str] = {}
    for ch in channels:
        cid = ch.get("id")
        name = ch.get("name") or ""
        if not cid:
            continue
        norm = normalize_channel_name(name)
        if norm:
            index[norm] = str(cid)
        index[name.lower()] = str(cid)
    return index


def match_channel(key: str, main_id: str, main_channels: list[dict], backup_index: dict[str, str]) -> str | None:
    main_ch = next((c for c in main_channels if str(c.get("id")) == main_id), None)
    if not main_ch:
        return None
    main_name = main_ch.get("name") or ""
    candidates = [
        normalize_channel_name(main_name),
        main_name.lower(),
    ]
    for alias in SLUG_ALIASES.get(key, ()):
        candidates.append(normalize_channel_name(alias))
        candidates.append(alias.lower())
    for cand in candidates:
        if cand and cand in backup_index:
            return backup_index[cand]
    return None


def match_role(key: str, main_id: str, main_roles: list[dict], backup_roles: list[dict]) -> str | None:
    main_role = next((r for r in main_roles if str(r.get("id")) == main_id), None)
    if not main_role:
        return None
    target_name = (main_role.get("name") or "").lower()
    for br in backup_roles:
        if (br.get("name") or "").lower() == target_name:
            return str(br["id"])
    return None


async def main():
    async with aiohttp.ClientSession() as session:
        _, main_channels = await fetch_json(
            session, f"https://discord.com/api/v10/guilds/{SHADOW_MAIN_GUILD_ID}/channels"
        )
        _, backup_channels = await fetch_json(
            session, f"https://discord.com/api/v10/guilds/{SHADOW_BACKUP_GUILD_ID}/channels"
        )
        _, main_roles = await fetch_json(
            session, f"https://discord.com/api/v10/guilds/{SHADOW_MAIN_GUILD_ID}/roles"
        )
        _, backup_roles = await fetch_json(
            session, f"https://discord.com/api/v10/guilds/{SHADOW_BACKUP_GUILD_ID}/roles"
        )

    if isinstance(main_channels, dict) and main_channels.get("message"):
        print("ERR main channels:", main_channels)
        return

    backup_index = build_name_index(backup_channels)
    reg = load_registry(force=True)
    backup_entry = reg["guilds"].setdefault(str(SHADOW_BACKUP_GUILD_ID), {"channels": {}, "roles": {}})
    backup_ch = backup_entry.setdefault("channels", {})
    backup_ro = backup_entry.setdefault("roles", {})

    print("=== CHANNEL MAPPING (ShadowBackup) ===")
    missing = []
    for key in CHANNEL_KEYS:
        main_id = str(_SHADOW_MAIN_CHANNELS[key])
        matched = match_channel(key, main_id, main_channels, backup_index)
        if matched:
            backup_ch[key] = matched
            print(f"  OK  {key}: {matched}")
        else:
            missing.append(key)
            print(f"  MISS {key} (main {main_id})")

    print("\n=== ROLE MAPPING (ShadowBackup) ===")
    for key in ROLE_KEYS:
        main_rid = str(_SHADOW_MAIN_ROLES[key])
        matched = match_role(key, main_rid, main_roles, backup_roles)
        if matched:
            backup_ro[key] = matched
            print(f"  OK  {key}: {matched}")
        else:
            missing.append(f"role:{key}")
            print(f"  MISS {key} (main {main_rid})")

    save_registry(reg)
    print(f"\nSaved {REGISTRY_PATH}")
    if missing:
        print("Manual fix required for:", ", ".join(missing))
    else:
        print("All keys matched.")


if __name__ == "__main__":
    asyncio.run(main())
