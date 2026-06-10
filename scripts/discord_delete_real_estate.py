"""ShadowAdmin: remove Real Estate category and all child channels."""

import asyncio
import json
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
GUILD = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_GUILD_ID"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

REAL_ESTATE_CATEGORY = "1513361355858509874"


async def delete_channel(session: aiohttp.ClientSession, channel_id: str, label: str) -> None:
    async with session.delete(f"https://discord.com/api/v10/channels/{channel_id}", headers=HEADERS) as resp:
        if resp.status == 404:
            print(f"SKIP (gone) {label} {channel_id}")
            return
        if resp.status not in (200, 204):
            text = await resp.text()
            raise RuntimeError(f"Failed to delete {label} {channel_id}: {resp.status} {text[:300]}")
        print(f"Deleted {label} {channel_id}")


async def main():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://discord.com/api/v10/guilds/{GUILD}/channels", headers=HEADERS) as resp:
            channels = await resp.json()

        children = [
            c for c in channels
            if c.get("parent_id") == REAL_ESTATE_CATEGORY and c.get("type") == 0
        ]
        children.sort(key=lambda c: c.get("position", 0))

        for ch in children:
            await delete_channel(session, ch["id"], ch.get("name", "channel"))

        await delete_channel(session, REAL_ESTATE_CATEGORY, "Real Estate category")
        print("Real Estate removed from Discord.")


if __name__ == "__main__":
    asyncio.run(main())
