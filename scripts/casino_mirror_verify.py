"""Verify casino floor panel on ShadowMain + ShadowBackup."""

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

CASINO_PANEL_TITLE = "ShadowSyn VIP Casino Floor"


async def fetch_messages(session: aiohttp.ClientSession, channel_id: int, limit: int = 25):
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit={limit}"
    async with session.get(url, headers=HEADERS) as resp:
        if resp.status != 200:
            return None, await resp.text()
        return await resp.json(), ""


def audit_casino_panel(messages: list) -> str:
    for msg in messages:
        for embed in msg.get("embeds", []):
            if embed.get("title") == CASINO_PANEL_TITLE:
                if msg.get("components"):
                    return "OK"
                return "PANEL_NO_BUTTONS"
    return "MISSING"


async def audit_guild(session: aiohttp.ClientSession, label: str, guild_id: int) -> tuple[str, bool]:
    cid = ch_id(guild_id, "casino")
    if not cid:
        return "NO_CHANNEL_ID", False
    messages, err = await fetch_messages(session, cid)
    if messages is None:
        return f"READ_FAIL: {err[:80]}", False
    status = audit_casino_panel(messages)
    return status, status == "OK"


async def main():
    load_registry(force=True)
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/v10/users/@me", headers=HEADERS) as resp:
            me = await resp.json()
            print(f"Auditing casino panel as {me.get('username')} ({me.get('id')})\n")

        all_ok = True
        for label, gid in (
            ("ShadowMain", SHADOW_MAIN_GUILD_ID),
            ("ShadowBackup", SHADOW_BACKUP_GUILD_ID),
        ):
            status, ok = await audit_guild(session, label, gid)
            all_ok = all_ok and ok
            print(f"=== {label} ({gid}) ===")
            print(f"  [{status}] casino floor panel")
            print()

        print("OVERALL:", "PASS" if all_ok else "REVIEW — run /casino_deploy on missing guild(s)")


if __name__ == "__main__":
    asyncio.run(main())
