"""Verify ShadowMain + ShadowBackup mirror panels via Discord API."""

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
    ch_id,
    load_registry,
)

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

PANEL_CHECKS = {
    "clips": ("clips", "🎬 Clips"),
    "steam_codes": ("steam_codes", "🎮 Steam Friend Codes"),
    "lobby_hub": ("lobby", "Welcome -ShadowSyn-"),
    "casino": ("casino", "ShadowSyn VIP Casino Floor"),
}

STEAM_THREAD_KEYS = ("steam_action_pvp", "steam_adventure_coop")


async def fetch_messages(session: aiohttp.ClientSession, channel_id: int, limit: int = 25) -> tuple[list | None, str]:
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            return None, await resp.text()
        return await resp.json(), ""


def has_panel(messages: list, title: str) -> bool:
    for msg in messages:
        for embed in msg.get("embeds", []):
            if embed.get("title") == title:
                return True
    return False


def has_components(messages: list, title: str) -> bool:
    for msg in messages:
        for embed in msg.get("embeds", []):
            if embed.get("title") == title and msg.get("components"):
                return True
    return False


def steam_thread_bound(messages: list) -> bool:
    markers = ("system bound", "system check", "registered this thread", "steam new releases")
    for msg in messages:
        content = (msg.get("content") or "").lower()
        if any(m in content for m in markers):
            return True
        for embed in msg.get("embeds", []):
            blob = f"{embed.get('title', '')} {embed.get('description', '')}".lower()
            if any(m in blob for m in markers):
                return True
    return False


async def audit_guild(session: aiohttp.ClientSession, label: str, guild_id: int) -> dict:
    results = {"label": label, "panels": {}, "steam": {}, "ok": True}
    for key, (ch_key, title) in PANEL_CHECKS.items():
        cid = ch_id(guild_id, ch_key)
        if not cid:
            results["panels"][key] = "NO_CHANNEL_ID"
            results["ok"] = False
            continue
        messages, err = await fetch_messages(session, cid)
        if messages is None:
            results["panels"][key] = f"READ_FAIL: {err[:80]}"
            results["ok"] = False
            continue
        found = has_panel(messages, title)
        interactive = has_components(messages, title)
        if found and interactive:
            results["panels"][key] = "OK"
        elif found:
            results["panels"][key] = "PANEL_NO_BUTTONS"
            results["ok"] = False
        else:
            results["panels"][key] = "MISSING"
            results["ok"] = False

    for st_key in STEAM_THREAD_KEYS:
        cid = ch_id(guild_id, st_key)
        if not cid:
            results["steam"][st_key] = "NO_CHANNEL_ID"
            results["ok"] = False
            continue
        messages, err = await fetch_messages(session, cid, limit=15)
        if messages is None:
            results["steam"][st_key] = f"READ_FAIL"
            results["ok"] = False
            continue
        results["steam"][st_key] = "OK" if steam_thread_bound(messages) else "CHECK_MANUALLY"

    return results


async def main():
    load_registry(force=True)
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/v10/users/@me", headers=HEADERS) as resp:
            me = await resp.json()
            print(f"Auditing as {me.get('username')} ({me.get('id')})\n")

        all_ok = True
        for label, gid in (
            ("ShadowMain", SHADOW_MAIN_GUILD_ID),
            ("ShadowBackup", SHADOW_BACKUP_GUILD_ID),
        ):
            r = await audit_guild(session, label, gid)
            all_ok = all_ok and r["ok"]
            print(f"=== {label} ({gid}) ===")
            for k, v in r["panels"].items():
                print(f"  [{v}] {k}")
            for k, v in r["steam"].items():
                print(f"  [{v}] {k}")
            print()

        print("OVERALL:", "PASS" if all_ok else "REVIEW — some items need attention")


if __name__ == "__main__":
    asyncio.run(main())
