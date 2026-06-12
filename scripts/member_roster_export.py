"""
ShadowAdmin: export Minion + Member roster for off-site disaster backup.

Usage:
  python scripts/member_roster_export.py --dry-run
  python scripts/member_roster_export.py
  python scripts/member_roster_export.py --csv
"""

import argparse
import asyncio
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
GUILD = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_GUILD_ID"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

MINION_ROLE_ID = "955600021502431233"
MEMBER_ROLE_ID = "955600320287887400"
SCHEMA_VERSION = 1

OUT_DIR = Path(r"C:\Users\josep\Desktop\Joe\Cursor\discord-bots\data")
JSON_PATH = OUT_DIR / "member_roster_backup.json"
CSV_PATH = OUT_DIR / "member_roster_backup.csv"


def build_display_label(username: str, global_name: str | None, server_nick: str | None) -> str:
    username = username or "unknown"
    if server_nick:
        return f"{server_nick} (@{username})"
    if global_name:
        return f"{global_name} (@{username})"
    return f"@{username}"


def role_labels(role_ids: list[str]) -> list[str]:
    labels: list[str] = []
    if MINION_ROLE_ID in role_ids:
        labels.append("minion")
    if MEMBER_ROLE_ID in role_ids:
        labels.append("member")
    return labels


def member_entry(raw: dict) -> dict | None:
    user = raw.get("user") or {}
    if user.get("bot"):
        return None
    role_ids = [str(r) for r in raw.get("roles", [])]
    labels = role_labels(role_ids)
    if not labels:
        return None

    username = user.get("username") or "unknown"
    global_name = user.get("global_name")
    server_nick = raw.get("nick")
    user_id = str(user.get("id"))
    now = datetime.now(timezone.utc).isoformat()

    return {
        "user_id": user_id,
        "username": username,
        "global_name": global_name,
        "server_nick": server_nick,
        "display_label": build_display_label(username, global_name, server_nick),
        "roles": labels,
        "still_in_guild": True,
        "invite_eligible": True,
        "dm_status": "unknown",
        "dm_last_checked": None,
        "dm_last_error": None,
        "first_recorded": now,
        "last_updated": now,
    }


async def fetch_all_members(session: aiohttp.ClientSession) -> list[dict]:
    members: list[dict] = []
    after = None
    while True:
        url = f"https://discord.com/api/v10/guilds/{GUILD}/members?limit=1000"
        if after:
            url += f"&after={after}"
        async with session.get(url, headers=HEADERS) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Member fetch failed ({resp.status}): {text[:300]}")
            batch = await resp.json()
        if not batch:
            break
        members.extend(batch)
        after = batch[-1]["user"]["id"]
        if len(batch) < 1000:
            break
        await asyncio.sleep(0.5)
    return members


def build_report(entries: dict[str, dict]) -> dict:
    stats = {
        "total_with_roles": len(entries),
        "minion_only": 0,
        "member_only": 0,
        "both_roles": 0,
    }
    for entry in entries.values():
        roles = entry.get("roles") or []
        has_minion = "minion" in roles
        has_member = "member" in roles
        if has_minion and has_member:
            stats["both_roles"] += 1
        elif has_minion:
            stats["minion_only"] += 1
        elif has_member:
            stats["member_only"] += 1
    return {
        "schema_version": SCHEMA_VERSION,
        "source_guild_id": GUILD,
        "last_full_sync": datetime.now(timezone.utc).isoformat(),
        "members": entries,
        "stats": stats,
    }


def write_csv(entries: dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "user_id",
                "username",
                "global_name",
                "server_nick",
                "display_label",
                "roles",
                "invite_eligible",
                "dm_status",
            ],
        )
        writer.writeheader()
        for entry in sorted(entries.values(), key=lambda row: row.get("display_label", "").lower()):
            writer.writerow(
                {
                    "user_id": entry.get("user_id"),
                    "username": entry.get("username"),
                    "global_name": entry.get("global_name") or "",
                    "server_nick": entry.get("server_nick") or "",
                    "display_label": entry.get("display_label"),
                    "roles": ",".join(entry.get("roles") or []),
                    "invite_eligible": entry.get("invite_eligible"),
                    "dm_status": entry.get("dm_status"),
                }
            )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Export Minion/Member roster off-site")
    parser.add_argument("--dry-run", action="store_true", help="Print counts only")
    parser.add_argument("--csv", action="store_true", help="Also write CSV beside JSON")
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        raw_members = await fetch_all_members(session)

    entries: dict[str, dict] = {}
    for raw in raw_members:
        entry = member_entry(raw)
        if entry:
            entries[entry["user_id"]] = entry

    report = build_report(entries)
    stats = report["stats"]
    print(f"Guild members scanned: {len(raw_members)}")
    print(f"Roster saved: {stats['total_with_roles']}")
    print(f"  minion only: {stats['minion_only']}")
    print(f"  member only: {stats['member_only']}")
    print(f"  both roles: {stats['both_roles']}")

    if args.dry_run:
        print("Dry run complete.")
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = JSON_PATH.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(
            {
                "schema_version": report["schema_version"],
                "source_guild_id": report["source_guild_id"],
                "last_full_sync": report["last_full_sync"],
                "members": report["members"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(JSON_PATH)
    print(f"JSON written: {JSON_PATH}")

    if args.csv:
        write_csv(entries, CSV_PATH)
        print(f"CSV written: {CSV_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
