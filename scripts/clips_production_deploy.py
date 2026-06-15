"""
Deploy clips ingest panel on ShadowMain and/or ShadowBackup (mirrors /clips_deploy).

Uses DISCORD_TOKEN from Railway (Shadow bot). Run with --discord-only after a normal deploy.
"""

import asyncio
import json
import os
import sys
import urllib.request
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

ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"
SHADOW_BOT_ID = "1401788343825727618"
THEME_PRIMARY = 0x2B0B35
INGEST_PANEL_TITLE = "🎬 Clips"
INGEST_PANEL_DESCRIPTION = (
    "Hit **Submit Clip** — paste a Medal / YouTube link or upload a file.\n"
    "Each clip gets its own thread."
)
INGEST_PANEL_FOOTER_PREFIX = "ShadowSyn Clips · "
PERSIST_LOCAL = ROOT / "data" / "clips_repo.json"
HOF_THREAD_NAME = "🏛️ Hall of Fame"

SEND_MESSAGES = 1 << 11
CREATE_PUBLIC_THREADS = 1 << 35
CREATE_PRIVATE_THREADS = 1 << 36
SEND_MESSAGES_IN_THREADS = 1 << 38
DENY_BITS = SEND_MESSAGES | CREATE_PUBLIC_THREADS | CREATE_PRIVATE_THREADS


def railway_token() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    token = os.getenv("RAILWAY_API_TOKEN", "")
    if not token:
        raise SystemExit("RAILWAY_API_TOKEN missing (.env.railway)")
    return token


def railway_gql(token: str, query: str, variables: dict | None = None) -> dict:
    body: dict = {"query": query}
    if variables:
        body["variables"] = variables
    req = urllib.request.Request(
        "https://backboard.railway.com/graphql/v2",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "ShadowSyn-Deploy/1.0",
        },
    )
    with urllib.request.urlopen(req) as resp:
        payload = json.loads(resp.read().decode())
    if payload.get("errors"):
        raise RuntimeError(json.dumps(payload["errors"], indent=2))
    return payload


def resolve_railway_ids(token: str) -> tuple[str, str]:
    data = railway_gql(
        token,
        """
        query ($id: String!) {
          project(id: $id) {
            environments { edges { node { id name } } }
            services { edges { node { id name } } }
          }
        }
        """,
        {"id": PROJECT_ID},
    )
    project = data["data"]["project"]
    env = next(
        (e["node"] for e in project["environments"]["edges"] if e["node"]["name"] == "production"),
        project["environments"]["edges"][0]["node"],
    )
    service = next(s["node"] for s in project["services"]["edges"] if s["node"]["name"] == SERVICE_NAME)
    return env["id"], service["id"]


def fetch_shadow_discord_token(railway: str, env_id: str, service_id: str) -> str:
    data = railway_gql(
        railway,
        """
        query ($projectId: String!, $environmentId: String!, $serviceId: String!) {
          variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
        }
        """,
        {
            "projectId": PROJECT_ID,
            "environmentId": env_id,
            "serviceId": service_id,
        },
    )
    variables = data["data"]["variables"]
    token = variables.get("DISCORD_TOKEN") or variables.get("discord_token")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not found in Railway service variables")
    return token


async def discord_api(session: aiohttp.ClientSession, token: str, method: str, path: str, payload=None):
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    async with session.request(
        method, f"https://discord.com/api/v10{path}", headers=headers, json=payload
    ) as resp:
        text = await resp.text()
        try:
            data = json.loads(text) if text else {}
        except json.JSONDecodeError:
            data = {"raw": text[:300]}
        return resp.status, data


def _is_ingest_panel(msg: dict) -> bool:
    embeds = msg.get("embeds") or []
    return bool(embeds and embeds[0].get("title") == INGEST_PANEL_TITLE)


async def purge_hof_threads(session: aiohttp.ClientSession, token: str, channel_id: int) -> int:
    removed = 0
    status, active = await discord_api(session, token, "GET", f"/channels/{channel_id}/threads/active")
    if status == 200 and isinstance(active, dict):
        for thread in active.get("threads") or []:
            if thread.get("name") != HOF_THREAD_NAME:
                continue
            st, _ = await discord_api(session, token, "DELETE", f"/channels/{thread['id']}")
            if st in (200, 204):
                removed += 1
    status, archived = await discord_api(
        session, token, "GET", f"/channels/{channel_id}/threads/archived/public"
    )
    if status == 200 and isinstance(archived, dict):
        for thread in archived.get("threads") or []:
            if thread.get("name") != HOF_THREAD_NAME:
                continue
            st, _ = await discord_api(session, token, "DELETE", f"/channels/{thread['id']}")
            if st in (200, 204):
                removed += 1
    return removed


async def lock_permissions(session: aiohttp.ClientSession, token: str, channel_id: int):
    status, ch = await discord_api(session, token, "GET", f"/channels/{channel_id}")
    if status != 200:
        raise RuntimeError(f"Channel fetch failed: {status} {ch}")

    patched = []
    for ow in ch.get("permission_overwrites", []):
        if ow.get("id") == SHADOW_BOT_ID:
            continue
        allow = int(ow.get("allow", 0))
        deny = int(ow.get("deny", 0))
        allow = (allow | SEND_MESSAGES_IN_THREADS) & ~DENY_BITS
        deny = deny | DENY_BITS
        patched.append({"id": ow["id"], "type": ow["type"], "allow": str(allow), "deny": str(deny)})

    guild_id = ch.get("guild_id")
    if guild_id and not any(o["id"] == guild_id for o in patched):
        patched.append({
            "id": guild_id,
            "type": 0,
            "allow": str(SEND_MESSAGES_IN_THREADS),
            "deny": str(DENY_BITS),
        })

    status, updated = await discord_api(
        session,
        token,
        "PATCH",
        f"/channels/{channel_id}",
        {"permission_overwrites": patched},
    )
    if status != 200:
        raise RuntimeError(f"Permission lock failed: {status} {updated}")
    print(f"  Permissions locked ({len(patched)} targets)")


async def remove_old_panels(session: aiohttp.ClientSession, token: str, channel_id: int):
    removed: set[str] = set()
    status, pins = await discord_api(session, token, "GET", f"/channels/{channel_id}/pins")
    if status == 200 and isinstance(pins, list):
        for item in pins:
            if not _is_ingest_panel(item):
                continue
            mid = item["id"]
            await discord_api(session, token, "DELETE", f"/channels/{channel_id}/pins/{mid}")
            await discord_api(session, token, "DELETE", f"/channels/{channel_id}/messages/{mid}")
            removed.add(mid)

    before = None
    for _ in range(5):
        path = f"/channels/{channel_id}/messages?limit=50"
        if before:
            path += f"&before={before}"
        status, batch = await discord_api(session, token, "GET", path)
        if status != 200 or not isinstance(batch, list) or not batch:
            break
        for item in batch:
            mid = item["id"]
            if mid in removed or not _is_ingest_panel(item):
                continue
            await discord_api(session, token, "DELETE", f"/channels/{channel_id}/messages/{mid}")
            removed.add(mid)
        before = batch[-1]["id"]
    if removed:
        print(f"  Removed {len(removed)} old panel(s)")


async def deploy_panel(session: aiohttp.ClientSession, token: str, channel_id: int) -> str:
    clips_data: dict = {}
    if PERSIST_LOCAL.exists():
        try:
            clips_data = json.loads(PERSIST_LOCAL.read_text(encoding="utf-8"))
        except Exception:
            clips_data = {}
    total = len(clips_data.get("clips") or {})
    panel_embed = {
        "title": INGEST_PANEL_TITLE,
        "description": INGEST_PANEL_DESCRIPTION,
        "color": THEME_PRIMARY,
        "footer": {"text": f"{INGEST_PANEL_FOOTER_PREFIX}{total:,} clips shared"},
    }
    components = [{
        "type": 1,
        "components": [{
            "type": 2,
            "style": 1,
            "label": "Submit Clip",
            "emoji": {"name": "🎬"},
            "custom_id": "clips_submit_panel",
        }],
    }]

    await remove_old_panels(session, token, channel_id)
    status, panel = await discord_api(
        session,
        token,
        "POST",
        f"/channels/{channel_id}/messages",
        {"embeds": [panel_embed], "components": components},
    )
    if status not in (200, 201):
        raise RuntimeError(f"Panel post failed: {status} {panel}")
    panel_id = str(panel["id"])
    print(f"  Panel posted: {panel_id}")
    return panel_id


async def deploy_guild(
    session: aiohttp.ClientSession,
    token: str,
    label: str,
    guild_id: int,
) -> str | None:
    channel_id = ch_id(guild_id, "clips")
    if not channel_id:
        print(f"  SKIP — no clips channel in registry")
        return None
    print(f"\n=== {label} ({guild_id}) — #{channel_id} ===")
    hof_removed = await purge_hof_threads(session, token, channel_id)
    if hof_removed:
        print(f"  Purged {hof_removed} Hall of Fame thread(s)")
    await lock_permissions(session, token, channel_id)
    return await deploy_panel(session, token, channel_id)


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--guild", choices=("main", "backup", "all"), default="all")
    args = parser.parse_args()

    load_registry(force=True)
    railway = railway_token()
    env_id, service_id = resolve_railway_ids(railway)
    discord_token = fetch_shadow_discord_token(railway, env_id, service_id)

    targets: list[tuple[str, int]] = []
    if args.guild in ("main", "all"):
        targets.append(("ShadowMain", SHADOW_MAIN_GUILD_ID))
    if args.guild in ("backup", "all"):
        targets.append(("ShadowBackup", SHADOW_BACKUP_GUILD_ID))

    panel_ids: dict[str, str] = {}
    async with aiohttp.ClientSession() as session:
        status, me = await discord_api(session, discord_token, "GET", "/users/@me")
        if status != 200:
            raise RuntimeError(f"Bot auth failed: {status} {me}")
        print(f"Deploying as {me.get('username')} ({me.get('id')})")
        if str(me.get("id")) != SHADOW_BOT_ID:
            print("WARNING: expected Shadow production bot")

        for label, gid in targets:
            pid = await deploy_guild(session, discord_token, label, gid)
            if pid:
                panel_ids[str(gid)] = pid

    print("\nDone.")
    for gid, pid in panel_ids.items():
        print(f"  guild {gid} panel_message_id={pid}")
    print("Run /clips_deploy once per guild in Discord to sync Railway /data panel ids (optional).")


if __name__ == "__main__":
    asyncio.run(main())
