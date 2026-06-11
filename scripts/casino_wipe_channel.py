"""ShadowAdmin: purge all messages in the VIP casino channel."""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

CASINO_CHANNEL_ID = "1468766727134249091"
BULK_DELETE_MAX_AGE_DAYS = 14


async def fetch_messages(session: aiohttp.ClientSession, channel_id: str) -> list[dict]:
    messages: list[dict] = []
    before = None
    while True:
        url = f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100"
        if before:
            url += f"&before={before}"
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Fetch failed ({resp.status}): {text[:300]}")
            batch = await resp.json()
        if not batch:
            break
        messages.extend(batch)
        before = batch[-1]["id"]
        if len(batch) < 100:
            break
        await asyncio.sleep(0.5)
    return messages


async def delete_message(session: aiohttp.ClientSession, channel_id: str, msg_id: str) -> int:
    for _ in range(5):
        async with session.delete(
            f"https://discord.com/api/v10/channels/{channel_id}/messages/{msg_id}",
            headers=HEADERS,
        ) as resp:
            if resp.status == 429:
                retry = float(resp.headers.get("Retry-After", "2"))
                await asyncio.sleep(retry + 0.5)
                continue
            return resp.status
    return 429


async def bulk_delete(session: aiohttp.ClientSession, channel_id: str, msg_ids: list[str]) -> int:
    async with session.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages/bulk-delete",
        headers={**HEADERS, "Content-Type": "application/json"},
        json={"messages": msg_ids},
    ) as resp:
        return resp.status


def message_age_days(msg: dict) -> float:
    ts = msg.get("timestamp", "")
    if not ts:
        return 999
    created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - created).total_seconds() / 86400


async def post_wipe_notice(session: aiohttp.ClientSession, channel_id: str) -> None:
    payload = {
        "embeds": [
            {
                "title": "🎰 VIP Casino Floor — Cleared",
                "description": (
                    "Channel wiped by **ShadowAdmin**.\n"
                    "Use `/gamble` for your private hub — **big wins & jackpots** post here."
                ),
                "color": 0x2B0B35,
            }
        ]
    }
    async with session.post(
        f"https://discord.com/api/v10/channels/{channel_id}/messages",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload,
    ) as resp:
        if resp.status not in (200, 201):
            text = await resp.text()
            print(f"Notice post failed ({resp.status}): {text[:200]}")


async def purge_all(session: aiohttp.ClientSession, channel_id: str) -> int:
    """Delete messages in batches until channel is empty."""
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
            status = await delete_message(session, channel_id, msg["id"])
            if status in (204, 404):
                deleted += 1
                if deleted % 25 == 0:
                    print(f"Progress: {deleted} deleted…")
            else:
                print(f"  Failed {msg['id']}: HTTP {status}")
            await asyncio.sleep(1.0)
    return deleted


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-notice", action="store_true")
    args = parser.parse_args()

    print(f"Target: casino channel {CASINO_CHANNEL_ID}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE DELETE'}")

    async with aiohttp.ClientSession() as session:
        if args.dry_run:
            messages = await fetch_messages(session, CASINO_CHANNEL_ID)
            print(f"Fetched {len(messages)} messages.")
            for msg in messages[:20]:
                author = msg.get("author", {}).get("username", "?")
                snippet = (msg.get("content") or "")[:40] or (
                    (msg.get("embeds") or [{}])[0].get("title", "")
                )
                print(f"  DEL {msg['id']} | {author} | {snippet!r}")
            if len(messages) > 20:
                print(f"  ... and {len(messages) - 20} more")
            print("Dry run complete.")
            return

        deleted = await purge_all(session, CASINO_CHANNEL_ID)
        print(f"Done. Deleted {deleted} messages.")

        if not args.no_notice:
            await post_wipe_notice(session, CASINO_CHANNEL_ID)
            print("Posted wipe notice.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(130)
