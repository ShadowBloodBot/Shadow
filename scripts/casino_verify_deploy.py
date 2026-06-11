"""Verify /gamble and casino slash commands are registered on production bot."""

import asyncio
import json
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
MCP = json.loads((ROOT / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
GUILD = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_GUILD_ID"]
NEEDED = {"gamble", "redemptions", "give_coins"}


async def main():
    headers = {"Authorization": f"Bot {TOKEN}"}
    async with aiohttp.ClientSession() as session:
        async with session.get("https://discord.com/api/v10/users/@me", headers=headers) as resp:
            me = await resp.json()
            if resp.status != 200:
                print(f"Bot check failed: {resp.status} {me}")
                return 1
            print(f"Bot online: {me.get('username')} ({me.get('id')})")

        app_id = me["id"]
        async with session.get(
            f"https://discord.com/api/v10/applications/{app_id}/guilds/{GUILD}/commands",
            headers=headers,
        ) as resp:
            cmds = await resp.json()
        if not isinstance(cmds, list):
            print(f"Command fetch failed: {cmds}")
            return 1

        names = {c["name"] for c in cmds}
        found = sorted(names & NEEDED)
        missing = sorted(NEEDED - names)
        print(f"Casino commands registered ({len(found)}/{len(NEEDED)}): {found}")
        if missing:
            print(f"Still missing (deploy may be in progress): {missing}")
            return 1
        gamble = next(c for c in cmds if c["name"] == "gamble")
        print(f"/gamble: {gamble.get('description')}")
        print("VERIFY_OK")
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
