"""Refresh lobby welcome hub embeds + buttons (game-roles replaces general-open)."""

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
)

ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"
SHADOW_BOT_ID = "1401788343825727618"
HUB_TITLE = "Welcome -ShadowSyn-"
THEME_PRIMARY = 0x2B0B35
MINION_BUTTON_ID = "hub_minion_grab"
SCAN_LIMIT = 100


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


def resolve_railway_ids(railway: str) -> tuple[str, str]:
    data = railway_gql(
        railway,
        """
        query ($id: String!) {
          project(id: $id) {
            environments { edges { node { id } } }
            services { edges { node { id name } } }
          }
        }
        """,
        {"id": PROJECT_ID},
    )
    project = data["data"]["project"]
    env = project["environments"]["edges"][0]["node"]
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


def channel_link(guild_id: int, key: str) -> str:
    cid = ch_id(guild_id, key)
    if cid is None:
        return f"https://discord.com/channels/{guild_id}"
    return f"https://discord.com/channels/{guild_id}/{cid}"


def hub_payload(guild_id: int) -> dict:
    game_roles = ch_id(guild_id, "game_roles")
    steam = ch_id(guild_id, "steam_codes")
    welcome = ch_id(guild_id, "welcome")
    description = (
        f"Grab your Starter role **[ Minion ]** so you can see\n"
        f"<#{game_roles}> & Share your <#{steam}>\n"
        f"Check out <#{welcome}> for anything else"
    )
    return {
        "embeds": [{
            "title": HUB_TITLE,
            "description": description,
            "color": THEME_PRIMARY,
        }],
        "components": [{
            "type": 1,
            "components": [
                {
                    "type": 2,
                    "style": 1,
                    "label": "Minion",
                    "emoji": {"name": "👻"},
                    "custom_id": MINION_BUTTON_ID,
                },
                {
                    "type": 2,
                    "style": 5,
                    "label": "Game-Roles",
                    "emoji": {"name": "🎮"},
                    "url": channel_link(guild_id, "game_roles"),
                },
                {
                    "type": 2,
                    "style": 5,
                    "label": "Steam-Codes",
                    "emoji": {"name": "📥"},
                    "url": channel_link(guild_id, "steam_codes"),
                },
                {
                    "type": 2,
                    "style": 5,
                    "label": "Welcome",
                    "emoji": {"name": "👋"},
                    "url": channel_link(guild_id, "welcome"),
                },
            ],
        }],
    }


def is_hub_message(msg: dict) -> bool:
    author = msg.get("author") or {}
    if author.get("id") != SHADOW_BOT_ID:
        return False
    embeds = msg.get("embeds") or []
    return bool(embeds and embeds[0].get("title") == HUB_TITLE)


async def api(session, token, method, path, payload=None):
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    async with session.request(
        method,
        f"https://discord.com/api/v10{path}",
        headers=headers,
        json=payload,
    ) as resp:
        text = await resp.text()
        data = json.loads(text) if text else {}
        return resp.status, data


async def fetch_lobby_messages(session, token, channel_id: int) -> list[dict]:
    messages: list[dict] = []
    before: str | None = None
    while len(messages) < SCAN_LIMIT:
        path = f"/channels/{channel_id}/messages?limit=100"
        if before:
            path += f"&before={before}"
        status, batch = await api(session, token, "GET", path)
        if status != 200 or not isinstance(batch, list) or not batch:
            break
        messages.extend(batch)
        before = batch[-1]["id"]
        if len(batch) < 100:
            break
    return messages[:SCAN_LIMIT]


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Refresh lobby welcome hub panels")
    parser.add_argument("--guild", choices=("main", "backup", "all"), default="all")
    args = parser.parse_args()

    targets: list[tuple[str, int]] = []
    if args.guild in ("main", "all"):
        targets.append(("ShadowMain", SHADOW_MAIN_GUILD_ID))
    if args.guild in ("backup", "all"):
        targets.append(("ShadowBackup", SHADOW_BACKUP_GUILD_ID))

    railway = railway_token()
    env_id, service_id = resolve_railway_ids(railway)
    token = fetch_shadow_discord_token(railway, env_id, service_id)

    async with aiohttp.ClientSession() as session:
        status, me = await api(session, token, "GET", "/users/@me")
        if status != 200:
            raise RuntimeError(f"Auth failed: {me}")
        print(f"Refreshing as {me.get('username')} ({me.get('id')})")

        for label, guild_id in targets:
            lobby_id = ch_id(guild_id, "lobby")
            if lobby_id is None:
                print(f"\n=== {label} — SKIP (no lobby in registry) ===")
                continue
            payload = hub_payload(guild_id)
            print(f"\n=== {label} ({guild_id}) ===")
            messages = await fetch_lobby_messages(session, token, lobby_id)
            hubs = [m for m in messages if is_hub_message(m)]
            print(f"Scanned {len(messages)} lobby messages · {len(hubs)} hub panels found")

            updated = 0
            skipped_old = 0
            for msg in hubs:
                mid = msg["id"]
                for attempt in range(3):
                    status, data = await api(
                        session,
                        token,
                        "PATCH",
                        f"/channels/{lobby_id}/messages/{mid}",
                        payload,
                    )
                    if status == 200:
                        updated += 1
                        print(f"  Updated {mid}")
                        break
                    if data.get("code") == 30046:
                        skipped_old += 1
                        print(f"  Skipped {mid} (edit cap on old message)")
                        break
                    retry = float(data.get("retry_after", 1.5))
                    if status == 429 and attempt < 2:
                        await asyncio.sleep(retry + 0.5)
                        continue
                    print(f"  Failed {mid} ({status}): {data}")
                    break
                else:
                    await asyncio.sleep(0.35)

            print(f"  {label}: {updated}/{len(hubs)} refreshed · {skipped_old} skipped (edit cap)")

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
