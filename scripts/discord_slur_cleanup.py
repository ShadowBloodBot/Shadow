"""
ShadowAdmin: scan Lobby + General-Open for slur terms and delete matching messages.

Usage:
  python scripts/discord_slur_cleanup.py --dry-run
  python scripts/discord_slur_cleanup.py --execute
  python scripts/discord_slur_cleanup.py --dry-run --channel 956725685014134785
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from content_filter import (  # noqa: E402
    FILTER_CHANNEL_IDS,
    GENERAL_OPEN_CHANNEL_ID,
    LOBBY_CHANNEL_ID,
    is_protected_hub_panel,
    match_slurs,
    searchable_text,
)

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

TARGET_CHANNELS = {
    str(LOBBY_CHANNEL_ID): "lobby",
    str(GENERAL_OPEN_CHANNEL_ID): "general-open",
}

AUDIT_PATH = Path(r"C:\Users\josep\Desktop\Joe\Cursor\discord-bots\data\slur_cleanup_audit.json")
BULK_DELETE_MAX_AGE_DAYS = 14


def message_searchable_text(msg: dict) -> str:
    return searchable_text(
        msg.get("content") or "",
        embeds=msg.get("embeds"),
        attachments=msg.get("attachments"),
    )


def match_message_slurs(msg: dict) -> list[str]:
    return match_slurs(message_searchable_text(msg))


def is_protected_hub_panel_message(msg: dict) -> bool:
    embeds = msg.get("embeds") or []
    if not embeds:
        return False
    return is_protected_hub_panel(embeds[0].get("title"))


def snippet(msg: dict, max_len: int = 80) -> str:
    content = (msg.get("content") or "").strip()
    if content:
        return content[:max_len]
    embeds = msg.get("embeds") or []
    if embeds:
        title = embeds[0].get("title") or ""
        desc = embeds[0].get("description") or ""
        combined = f"{title} {desc}".strip()
        if combined:
            return combined[:max_len]
    attachments = msg.get("attachments") or []
    if attachments:
        return attachments[0].get("filename", "")[:max_len]
    return ""


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
                raise RuntimeError(
                    f"Fetch failed for channel {channel_id} ({resp.status}): {text[:300]}"
                )
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
    for _ in range(8):
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


def scan_channel(channel_id: str, messages: list[dict]) -> list[dict]:
    hits: list[dict] = []
    for msg in messages:
        if is_protected_hub_panel_message(msg):
            continue
        terms = match_message_slurs(msg)
        if not terms:
            continue
        author = msg.get("author") or {}
        hits.append(
            {
                "channel_id": channel_id,
                "channel_name": TARGET_CHANNELS[channel_id],
                "message_id": msg["id"],
                "author_id": author.get("id"),
                "author": author.get("username", "?"),
                "timestamp": msg.get("timestamp"),
                "matched_terms": terms,
                "snippet": snippet(msg),
            }
        )
    return hits


def write_audit(report: dict) -> None:
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = AUDIT_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    tmp.replace(AUDIT_PATH)


async def delete_matches(
    session: aiohttp.ClientSession,
    channel_id: str,
    messages_by_id: dict[str, dict],
    hit_ids: list[str],
) -> tuple[int, int]:
    deleted = 0
    errors = 0
    deleted_ids: set[str] = set()
    to_delete = [messages_by_id[mid] for mid in hit_ids if mid in messages_by_id]

    bulk_ids = [m["id"] for m in to_delete if message_age_days(m) < BULK_DELETE_MAX_AGE_DAYS]
    for i in range(0, len(bulk_ids), 100):
        chunk = bulk_ids[i : i + 100]
        if len(chunk) < 2:
            continue
        status = await bulk_delete(session, channel_id, chunk)
        if status == 204:
            deleted += len(chunk)
            deleted_ids.update(chunk)
            print(f"  Bulk deleted {len(chunk)} in {TARGET_CHANNELS[channel_id]}")
        else:
            errors += len(chunk)
            print(f"  Bulk delete failed HTTP {status} ({len(chunk)} msgs)")
        await asyncio.sleep(1.0)

    for msg in to_delete:
        if msg["id"] in deleted_ids:
            continue
        status = await delete_message(session, channel_id, msg["id"])
        if status in (204, 404):
            deleted += 1
        else:
            errors += 1
            print(f"  Failed {msg['id']}: HTTP {status}")
        await asyncio.sleep(0.75)

    return deleted, errors


async def process_channel(
    session: aiohttp.ClientSession,
    channel_id: str,
    execute: bool,
) -> dict:
    name = TARGET_CHANNELS[channel_id]
    print(f"\n=== {name} ({channel_id}) ===")
    messages = await fetch_messages(session, channel_id)
    print(f"Fetched {len(messages)} messages.")
    messages_by_id = {m["id"]: m for m in messages}
    hits = scan_channel(channel_id, messages)
    print(f"Matches: {len(hits)}")
    for hit in hits:
        print(
            f"  {hit['channel_name']} | {hit['message_id']} | {hit['author']} | "
            f"{','.join(hit['matched_terms'])} | {hit['snippet']!r}"
        )

    deleted = 0
    errors = 0
    if execute and hits:
        hit_ids = [h["message_id"] for h in hits]
        deleted, errors = await delete_matches(session, channel_id, messages_by_id, hit_ids)

    return {
        "channel_id": channel_id,
        "channel_name": name,
        "messages_scanned": len(messages),
        "matches": hits,
        "deleted": deleted,
        "errors": errors,
    }


async def verify_clean(session: aiohttp.ClientSession, channel_ids: list[str]) -> bool:
    remaining = 0
    for channel_id in channel_ids:
        messages = await fetch_messages(session, channel_id)
        hits = scan_channel(channel_id, messages)
        remaining += len(hits)
        if hits:
            print(f"  Remaining in {TARGET_CHANNELS[channel_id]}: {len(hits)}")
    return remaining == 0


async def main() -> None:
    parser = argparse.ArgumentParser(description="ShadowAdmin slur cleanup for Lobby + General-Open")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Audit only — no deletes")
    group.add_argument("--execute", action="store_true", help="Delete matching messages")
    parser.add_argument(
        "--channel",
        choices=list(TARGET_CHANNELS.keys()),
        help="Limit to a single channel ID",
    )
    args = parser.parse_args()

    channel_ids = [args.channel] if args.channel else list(TARGET_CHANNELS.keys())
    mode = "DRY RUN" if args.dry_run else "LIVE DELETE"
    print(f"ShadowAdmin slur cleanup — {mode}")
    print(f"Channels: {', '.join(TARGET_CHANNELS[c] for c in channel_ids)}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": mode.lower().replace(" ", "_"),
        "channels": [],
        "total_matches": 0,
        "total_deleted": 0,
        "total_errors": 0,
        "verified_clean": None,
    }

    async with aiohttp.ClientSession() as session:
        for channel_id in channel_ids:
            result = await process_channel(session, channel_id, execute=args.execute)
            report["channels"].append(result)
            report["total_matches"] += len(result["matches"])
            report["total_deleted"] += result["deleted"]
            report["total_errors"] += result["errors"]

        if args.execute:
            print("\nVerifying zero remaining matches...")
            report["verified_clean"] = await verify_clean(session, channel_ids)
            if report["verified_clean"]:
                print("Verification passed — no remaining matches.")
            else:
                print("Verification FAILED — matches still present.", file=sys.stderr)

    write_audit(report)
    print(f"\nAudit written: {AUDIT_PATH}")
    print(
        f"Summary: {report['total_matches']} match(es), "
        f"{report['total_deleted']} deleted, {report['total_errors']} error(s)"
    )

    if args.execute and report["verified_clean"] is False:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
