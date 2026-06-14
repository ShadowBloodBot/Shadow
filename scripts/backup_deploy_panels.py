"""Deploy panels and steam thread bindings on ShadowBackup (and optionally ShadowMain)."""

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

STEAM_FILTERS = {
    "steam_action_pvp": "Action, PvP",
    "steam_adventure_coop": "Adventure, Co-op",
}


async def post_panel(session, guild_id: int, channel_key: str, title: str, description: str, components=None):
    cid = ch_id(guild_id, channel_key)
    if not cid:
        print(f"  SKIP {channel_key} — no channel id for guild {guild_id}")
        return
    payload = {"embeds": [{"title": title, "description": description, "color": 0x2B0B35}]}
    if components:
        payload["components"] = components
    url = f"https://discord.com/api/v10/channels/{cid}/messages"
    async with session.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload) as resp:
        data = await resp.json()
        if resp.status >= 400:
            print(f"  ERR {channel_key}: {data}")
        else:
            print(f"  OK  {channel_key} panel -> message {data.get('id')}")


async def bind_steam_threads(session, guild_id: int):
    for key, filt in STEAM_FILTERS.items():
        cid = ch_id(guild_id, key)
        if not cid:
            continue
        msg = (
            f"✅ **ShadowAdmin** registered this thread for exclusive Steam new-release routing.\n\n"
            f"Filter: **{filt or 'catch-all'}**"
        )
        url = f"https://discord.com/api/v10/channels/{cid}/messages"
        async with session.post(
            url,
            headers={**HEADERS, "Content-Type": "application/json"},
            json={"content": msg},
        ) as resp:
            print(f"  steam bind {key}: HTTP {resp.status}")


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--guild", choices=("backup", "main", "all"), default="backup")
    args = parser.parse_args()

    load_registry(force=True)
    targets = []
    if args.guild in ("backup", "all"):
        targets.append(("ShadowBackup", SHADOW_BACKUP_GUILD_ID))
    if args.guild in ("main", "all"):
        targets.append(("ShadowMain", SHADOW_MAIN_GUILD_ID))

    async with aiohttp.ClientSession() as session:
        for label, gid in targets:
            print(f"\n=== {label} ({gid}) ===")
            print("Note: full panel components require /clips_deploy and /steam_codes_deploy in Discord.")
            await bind_steam_threads(session, gid)
    print("\nRun /clips_deploy and /steam_codes_deploy in each guild for interactive panels.")


if __name__ == "__main__":
    asyncio.run(main())
