"""Compare thread-related permissions: ShadowMain vs ShadowBackup (ShadowAdmin read-only)."""

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.guild_registry import (  # noqa: E402
    CHANNEL_KEYS,
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    ch_id,
    load_registry,
    normalize_channel_name,
)

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}"}

THREAD_PERM_BITS = {
    "MANAGE_THREADS": 1 << 34,
    "CREATE_PUBLIC_THREADS": 1 << 35,
    "CREATE_PRIVATE_THREADS": 1 << 36,
    "SEND_MESSAGES_IN_THREADS": 1 << 38,
}

THREAD_CHANNEL_TYPES = {10, 11, 12, 15}  # news_thread, public, private, forum
PARENT_TYPES = {0, 5, 15}  # text, announce, forum


def decode_thread_bits(val: int) -> set[str]:
    if val & (1 << 3):
        return {"ADMINISTRATOR"}
    return {n for n, b in THREAD_PERM_BITS.items() if val & b}


def norm_overwrite(ow: dict, role_names: dict[str, str]) -> dict:
    oid = str(ow.get("id", ""))
    otype = ow.get("type")
    if otype == 0:
        target = role_names.get(oid, f"role:{oid}")
    elif otype == 1:
        target = f"member:{oid}"
    else:
        target = f"unknown:{oid}"
    allow = int(ow.get("allow", "0"))
    deny = int(ow.get("deny", "0"))
    return {
        "target": target,
        "type": otype,
        "allow": sorted(decode_thread_bits(allow)),
        "deny": sorted(decode_thread_bits(deny)),
    }


def thread_parent_snapshot(ch: dict, role_names: dict[str, str]) -> dict:
    snap = {
        "type": ch.get("type"),
        "name": ch.get("name"),
        "overwrites": sorted(
            (norm_overwrite(ow, role_names) for ow in ch.get("permission_overwrites") or []),
            key=lambda x: x["target"],
        ),
    }
    for key in (
        "default_auto_archive_duration",
        "default_thread_rate_limit_per_user",
        "flags",
        "available_tags",
        "default_reaction_emoji",
        "default_sort_order",
        "default_forum_layout",
    ):
        if key in ch:
            snap[key] = ch.get(key)
    return snap


async def fetch_json(session: aiohttp.ClientSession, url: str):
    async with session.get(url, headers=HEADERS) as resp:
        return resp.status, await resp.json()


def build_role_names(roles: list[dict]) -> dict[str, str]:
    return {str(r["id"]): (r.get("name") or "").lower() for r in roles if r.get("id")}


def match_channel(main_ch: dict, backup_by_norm: dict[str, dict]) -> dict | None:
    name = main_ch.get("name") or ""
    for cand in (normalize_channel_name(name), name.lower()):
        if cand and cand in backup_by_norm:
            return backup_by_norm[cand]
    return None


def diff_snapshots(main_snap: dict, backup_snap: dict) -> list[str]:
    issues = []
    if main_snap.get("type") != backup_snap.get("type"):
        issues.append(f"type main={main_snap.get('type')} backup={backup_snap.get('type')}")
    for key in (
        "default_auto_archive_duration",
        "default_thread_rate_limit_per_user",
        "flags",
        "default_sort_order",
        "default_forum_layout",
    ):
        mv, bv = main_snap.get(key), backup_snap.get(key)
        if mv != bv:
            issues.append(f"{key}: main={mv!r} backup={bv!r}")
    main_ow = {o["target"]: o for o in main_snap.get("overwrites", [])}
    backup_ow = {o["target"]: o for o in backup_snap.get("overwrites", [])}
    all_targets = sorted(set(main_ow) | set(backup_ow))
    for target in all_targets:
        mo = main_ow.get(target)
        bo = backup_ow.get(target)
        if mo is None:
            issues.append(f"overwrite missing on MAIN: {target} (backup allow={bo.get('allow')} deny={bo.get('deny')})")
        elif bo is None:
            issues.append(f"overwrite missing on BACKUP: {target} (main allow={mo.get('allow')} deny={mo.get('deny')})")
        elif mo.get("allow") != bo.get("allow") or mo.get("deny") != bo.get("deny"):
            issues.append(
                f"overwrite mismatch {target}: "
                f"main allow={mo.get('allow')} deny={mo.get('deny')} | "
                f"backup allow={bo.get('allow')} deny={bo.get('deny')}"
            )
    return issues


async def audit_guild_threads(session: aiohttp.ClientSession, guild_id: int) -> dict:
    _, channels = await fetch_json(session, f"https://discord.com/api/v10/guilds/{guild_id}/channels")
    _, roles = await fetch_json(session, f"https://discord.com/api/v10/guilds/{guild_id}/roles")
    role_names = build_role_names(roles if isinstance(roles, list) else [])

    parents = [c for c in channels if c.get("type") in PARENT_TYPES]
    threads = [c for c in channels if c.get("type") in THREAD_CHANNEL_TYPES]

    parent_snaps = {c["id"]: thread_parent_snapshot(c, role_names) for c in parents}
    thread_snaps = {c["id"]: thread_parent_snapshot(c, role_names) for c in threads}

    active_threads: list[dict] = []
    for parent in parents:
        pid = parent["id"]
        status, data = await fetch_json(
            session,
            f"https://discord.com/api/v10/channels/{pid}/threads/active",
        )
        if status == 200 and isinstance(data, dict):
            for t in data.get("threads") or []:
                active_threads.append(t)

    return {
        "role_names": role_names,
        "parents": parents,
        "threads_in_tree": threads,
        "parent_snaps": parent_snaps,
        "thread_snaps": thread_snaps,
        "active_threads": active_threads,
    }


async def main():
    load_registry(force=True)
    async with aiohttp.ClientSession() as session:
        _, me = await fetch_json(session, "https://discord.com/api/v10/users/@me")
        print(f"Auditing as {me.get('username')} ({me.get('id')})\n")

        main = await audit_guild_threads(session, SHADOW_MAIN_GUILD_ID)
        backup = await audit_guild_threads(session, SHADOW_BACKUP_GUILD_ID)

        backup_by_norm: dict[str, dict] = {}
        for ch in backup["parents"]:
            name = ch.get("name") or ""
            for cand in (normalize_channel_name(name), name.lower()):
                if cand:
                    backup_by_norm[cand] = ch

        print("=== REGISTRY CHANNELS (thread parent settings) ===")
        registry_issues = []
        for key in CHANNEL_KEYS:
            main_id = ch_id(SHADOW_MAIN_GUILD_ID, key)
            backup_id = ch_id(SHADOW_BACKUP_GUILD_ID, key)
            main_ch = next((c for c in main["parents"] if str(c["id"]) == str(main_id)), None)
            backup_ch = next((c for c in backup["parents"] if str(c["id"]) == str(backup_id)), None)
            if not main_ch or not backup_ch:
                registry_issues.append(f"{key}: channel missing main={bool(main_ch)} backup={bool(backup_ch)}")
                print(f"  [MISS] {key}")
                continue
            ms = thread_parent_snapshot(main_ch, main["role_names"])
            bs = thread_parent_snapshot(backup_ch, backup["role_names"])
            issues = diff_snapshots(ms, bs)
            if issues:
                registry_issues.extend([f"{key}: {i}" for i in issues])
                print(f"  [DIFF] {key} ({main_ch.get('name')!r})")
                for i in issues:
                    print(f"         {i}")
            else:
                print(f"  [OK]   {key} ({main_ch.get('name')!r})")

        print("\n=== ALL THREAD-CAPABLE PARENTS (matched by channel name) ===")
        parent_issues = []
        matched = 0
        unmatched_main = []
        for main_ch in main["parents"]:
            backup_ch = match_channel(main_ch, backup_by_norm)
            if not backup_ch:
                unmatched_main.append(main_ch.get("name"))
                continue
            matched += 1
            ms = thread_parent_snapshot(main_ch, main["role_names"])
            bs = thread_parent_snapshot(backup_ch, backup["role_names"])
            issues = diff_snapshots(ms, bs)
            if issues:
                parent_issues.append((main_ch.get("name"), issues))
        print(f"Matched {matched} parent channels by name")
        if unmatched_main:
            print(f"Unmatched on Backup ({len(unmatched_main)}): {', '.join(unmatched_main[:15])}")
            if len(unmatched_main) > 15:
                print(f"  ... +{len(unmatched_main) - 15} more")
        if parent_issues:
            print(f"\nParent permission diffs ({len(parent_issues)}):")
            for name, issues in parent_issues[:25]:
                print(f"  [DIFF] {name!r}")
                for i in issues:
                    print(f"         {i}")
            if len(parent_issues) > 25:
                print(f"  ... +{len(parent_issues) - 25} more channels with diffs")
        else:
            print("All matched parents: thread overwrites identical")

        print("\n=== ACTIVE THREADS (sample overwrites vs parent channel) ===")
        thread_diffs = []
        for main_t in main["active_threads"][:50]:
            tname = main_t.get("name") or ""
            parent_id = main_t.get("parent_id")
            main_parent = next((c for c in main["parents"] if c["id"] == parent_id), None)
            if not main_parent:
                continue
            backup_parent = match_channel(main_parent, backup_by_norm)
            if not backup_parent:
                continue
            # find backup thread by name under matched parent
            status, data = await fetch_json(
                session,
                f"https://discord.com/api/v10/channels/{backup_parent['id']}/threads/active",
            )
            backup_threads = (data.get("threads") or []) if status == 200 and isinstance(data, dict) else []
            backup_t = next(
                (t for t in backup_threads if (t.get("name") or "").lower() == tname.lower()),
                None,
            )
            if not backup_t:
                thread_diffs.append(f"active thread {tname!r} under {main_parent.get('name')!r}: missing on Backup")
                continue
            ms = thread_parent_snapshot(main_t, main["role_names"])
            bs = thread_parent_snapshot(backup_t, backup["role_names"])
            issues = diff_snapshots(ms, bs)
            if issues:
                thread_diffs.append(f"active thread {tname!r} under {main_parent.get('name')!r}: {issues}")

        if thread_diffs:
            for line in thread_diffs[:20]:
                print(f"  [DIFF] {line}")
            if len(thread_diffs) > 20:
                print(f"  ... +{len(thread_diffs) - 20} more")
        else:
            print("  No active-thread overwrite diffs in sampled threads (or none active)")

        total_issues = len(registry_issues) + len(parent_issues) + len(thread_diffs)
        print(f"\n=== SUMMARY ===")
        print(f"Registry channels checked: {len(CHANNEL_KEYS)}")
        print(f"Registry diffs: {len(registry_issues)}")
        print(f"All-parent diffs: {len(parent_issues)}")
        print(f"Active thread diffs: {len(thread_diffs)}")
        print(f"OVERALL: {'PASS — thread permissions match' if total_issues == 0 else 'REVIEW — mismatches found'}")

        out_path = (
            Path(r"C:\Users\josep\Desktop\Joe\Cursor\discord-bots\data")
            / "thread_permissions_mirror_audit.json"
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "registry_issues": registry_issues,
                    "parent_issues": [
                        {"channel": n, "issues": i} for n, i in parent_issues
                    ],
                    "thread_diffs": thread_diffs,
                    "unmatched_main_parents": unmatched_main,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nFull report: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
