"""ShadowAdmin: finish purging steam-codes channel (rate-limit safe)."""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

STEAM_CODES_CHANNEL_ID = "961870662006345798"
SHADOW_BOT_ID = "1401788343825727618"
PANEL_TITLE = "🎮 Steam Friend Codes"


async def delete_message(session: aiohttp.ClientSession, channel_id: str, msg_id: str) -> int:
    for _ in range(8):
        async with session.delete(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{msg_id}",
            headers=HEADERS,
        ) as resp:
            if resp.status == 429:
                retry = float(resp.headers.get("Retry-After", "2"))
                print(f"  Rate limited — waiting {retry}s")
                await asyncio.sleep(retry + 0.5)
                continue
            return resp.status
    return 429


async def purge_all(session: aiohttp.ClientSession, channel_id: str) -> int:
    deleted = 0
    while True:
        async with session.get(
            f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100",
            headers=HEADERS,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Fetch failed ({resp.status}): {text[:300]}")
            batch = await resp.json()
        if not batch:
            break
        for msg in batch:
            author = msg.get("author", {})
            embeds = msg.get("embeds") or []
            title = embeds[0].get("title") if embeds else ""
            if author.get("id") == SHADOW_BOT_ID and title == PANEL_TITLE:
                print(f"  Keeping panel {msg['id']}")
                continue
            status = await delete_message(session, channel_id, msg["id"])
            if status in (204, 404):
                deleted += 1
                author_name = author.get("username", "?")
                snippet = (msg.get("content") or "")[:40]
                print(f"  Deleted {deleted}: {author_name} | {snippet!r}")
            else:
                print(f"  FAILED {msg['id']}: HTTP {status}")
            await asyncio.sleep(1.1)
    return deleted


async def count_remaining(session: aiohttp.ClientSession, channel_id: str) -> int:
    async with session.get(
        f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100",
        headers=HEADERS,
    ) as resp:
        batch = await resp.json()
        return len(batch) if isinstance(batch, list) else 0


async def main():
    dry_run = "--dry-run" in sys.argv
    print(f"Target: steam-codes channel {STEAM_CODES_CHANNEL_ID}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE DELETE'}")

    async with aiohttp.ClientSession() as session:
        remaining = await count_remaining(session, STEAM_CODES_CHANNEL_ID)
        print(f"Messages before: {remaining}")

        if dry_run:
            print("Dry run — no deletes.")
            return

        deleted = await purge_all(session, STEAM_CODES_CHANNEL_ID)
        remaining = await count_remaining(session, STEAM_CODES_CHANNEL_ID)
        print(f"\nDone. Deleted {deleted}. Remaining: {remaining}")


if __name__ == "__main__":
    asyncio.run(main())
