"""
Full clips production deploy:
1. Trigger Railway redeploy (latest main)
2. Lock gallery permissions
3. Post/pin Shadow bot ingest panel + Hall of Fame thread

Uses DISCORD_TOKEN from Railway (Shadow bot), never printed or committed.
"""

import asyncio
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.railway"
PERSIST_LOCAL = ROOT / "data" / "clips_repo.json"

PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"
CLIPS_CHANNEL_ID = "955609588470808657"
SHADOW_BOT_ID = "1401788343825727618"
THEME_PRIMARY = 0x2B0B35

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


def trigger_redeploy(railway: str, env_id: str, service_id: str):
    data = railway_gql(
        railway,
        """
        mutation ($serviceId: String!, $environmentId: String!) {
          serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId)
        }
        """,
        {"serviceId": service_id, "environmentId": env_id},
    )
    dep_id = data.get("data", {}).get("serviceInstanceDeploy")
    print(f"Railway redeploy triggered: {dep_id}")


async def discord_api(session: aiohttp.ClientSession, token: str, method: str, path: str, payload=None):
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    async with session.request(
        method, f"https://discord.com/api/v10{path}", headers=headers, json=payload
    ) as resp:
        text = await resp.text()
        data = json.loads(text) if text else {}
        return resp.status, data


async def lock_permissions(session: aiohttp.ClientSession, token: str):
    status, ch = await discord_api(session, token, "GET", f"/channels/{CLIPS_CHANNEL_ID}")
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
    if not any(o["id"] == guild_id for o in patched):
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
        f"/channels/{CLIPS_CHANNEL_ID}",
        {"permission_overwrites": patched},
    )
    if status != 200:
        raise RuntimeError(f"Permission lock failed: {status} {updated}")
    print(f"Gallery permissions locked ({len(patched)} targets)")


async def deploy_panel(session: aiohttp.ClientSession, token: str) -> tuple[str, str | None]:
    panel_embed = {
        "title": "🎬 Clips",
        "description": (
            "**Submit Clip** → pick a category → Medal / YouTube link or PC upload.\n"
            "Chat in each clip's thread. 🔥 votes can move clips to the **Hall of Fame**."
        ),
        "color": THEME_PRIMARY,
        "footer": {"text": "ShadowSyn Clips"},
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

    status, me = await discord_api(session, token, "GET", "/users/@me")
    if status != 200:
        raise RuntimeError(f"Bot auth failed: {status} {me}")
    print(f"Discord deploy as {me.get('username')} ({me.get('id')})")
    if str(me.get("id")) != SHADOW_BOT_ID:
        print("WARNING: expected Shadow production bot")

    panel_id = None
    repo = {}
    if PERSIST_LOCAL.exists():
        try:
            repo = json.loads(PERSIST_LOCAL.read_text(encoding="utf-8"))
            panel_id = repo.get("panel_message_id")
        except Exception:
            pass

    if panel_id:
        status, _ = await discord_api(
            session,
            token,
            "PATCH",
            f"/channels/{CLIPS_CHANNEL_ID}/messages/{panel_id}",
            {"embeds": [panel_embed], "components": components},
        )
        if status == 200:
            print(f"Panel updated: {panel_id}")
        else:
            panel_id = None

    if not panel_id:
        status, panel = await discord_api(
            session,
            token,
            "POST",
            f"/channels/{CLIPS_CHANNEL_ID}/messages",
            {"embeds": [panel_embed], "components": components},
        )
        if status not in (200, 201):
            raise RuntimeError(f"Panel post failed: {status} {panel}")
        panel_id = panel["id"]
        print(f"Panel posted: {panel_id}")

    await discord_api(session, token, "PUT", f"/channels/{CLIPS_CHANNEL_ID}/pins/{panel_id}")

    hof_thread_id = repo.get("hof_thread_id")
    if hof_thread_id:
        status, thread = await discord_api(session, token, "GET", f"/channels/{hof_thread_id}")
        if status == 200:
            print(f"HOF thread reused: {hof_thread_id}")
            return str(panel_id), str(hof_thread_id)

    status, thread = await discord_api(
        session,
        token,
        "POST",
        f"/channels/{CLIPS_CHANNEL_ID}/messages/{panel_id}/threads",
        {"name": "🏛️ Hall of Fame", "auto_archive_duration": 10080},
    )
    hof_id = None
    if status in (200, 201):
        hof_id = thread.get("id")
        await discord_api(session, token, "PATCH", f"/channels/{hof_id}", {"locked": True})
        print(f"HOF thread created: {hof_id}")
    else:
        print(f"HOF thread warning: {status} {thread}")

    return str(panel_id), hof_id


async def main():
    skip_railway = "--skip-railway" in sys.argv
    railway = railway_token()
    env_id, service_id = resolve_railway_ids(railway)

    if not skip_railway:
        trigger_redeploy(railway, env_id, service_id)
        print("Waiting 90s for Railway container boot...")
        time.sleep(90)

    discord_token = fetch_shadow_discord_token(railway, env_id, service_id)

    async with aiohttp.ClientSession() as session:
        await lock_permissions(session, discord_token)
        panel_id, hof_id = await deploy_panel(session, discord_token)

    print("Clips production deploy complete.")
    print(f"  panel_message_id={panel_id}")
    print(f"  hof_thread_id={hof_id}")
    print("Run /clips_deploy in Discord once if bot persistence file differs on Railway volume.")


if __name__ == "__main__":
    asyncio.run(main())
