"""Refresh welcome channel panel (embed + invite link button)."""

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
    channel_url,
)
from cogs.welcome import (  # noqa: E402
    MINION_BUTTON_ID,
    PANEL_TITLE,
    VANITY_INVITE_URL,
    build_welcome_embed,
)

ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"
SHADOW_BOT_ID = "1401788343825727618"


def railway_token() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("RAILWAY_API_TOKEN missing")


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


def fetch_shadow_discord_token() -> str:
    railway = railway_token()
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
    env_id = project["environments"]["edges"][0]["node"]["id"]
    service_id = next(
        s["node"]["id"] for s in project["services"]["edges"]
        if s["node"]["name"] == SERVICE_NAME
    )
    vars_data = railway_gql(
        railway,
        """
        query ($projectId: String!, $environmentId: String!, $serviceId: String!) {
          variables(projectId: $projectId, environmentId: $environmentId, serviceId: $serviceId)
        }
        """,
        {"projectId": PROJECT_ID, "environmentId": env_id, "serviceId": service_id},
    )
    variables = vars_data["data"]["variables"]
    token = variables.get("DISCORD_TOKEN") or variables.get("discord_token")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not found")
    return token


def panel_payload(guild_id: int) -> dict:
    embed = build_welcome_embed(guild_id)
    return {
        "embeds": [embed.to_dict()],
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
                    "url": channel_url(guild_id, "game_roles"),
                },
                {
                    "type": 2,
                    "style": 5,
                    "label": "Steam-Codes",
                    "emoji": {"name": "📥"},
                    "url": channel_url(guild_id, "steam_codes"),
                },
                {
                    "type": 2,
                    "style": 5,
                    "label": "Invite Friends",
                    "emoji": {"name": "🔗"},
                    "url": VANITY_INVITE_URL,
                },
            ],
        }],
    }


async def api(session, token, method, path, payload=None):
    headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
    async with session.request(
        method, f"https://discord.com/api/v10{path}", headers=headers, json=payload
    ) as resp:
        text = await resp.text()
        return resp.status, json.loads(text) if text else {}


def is_welcome_panel(msg: dict) -> bool:
    author = msg.get("author") or {}
    if author.get("id") != SHADOW_BOT_ID:
        return False
    embeds = msg.get("embeds") or []
    return bool(embeds and embeds[0].get("title") == PANEL_TITLE)


async def deploy_guild(session, token, label: str, guild_id: int) -> None:
    welcome_id = ch_id(guild_id, "welcome")
    if welcome_id is None:
        print(f"\n=== {label} — SKIP (no welcome in registry) ===")
        return
    payload = panel_payload(guild_id)
    print(f"\n=== {label} ({guild_id}) ===")

    messages: list[dict] = []
    for path in (
        f"/channels/{welcome_id}/pins",
        f"/channels/{welcome_id}/messages?limit=30",
    ):
        status, data = await api(session, token, "GET", path)
        if status == 200 and isinstance(data, list):
            for m in data:
                if m not in messages:
                    messages.append(m)

    panels = [m for m in messages if is_welcome_panel(m)]
    if not panels:
        status, panel = await api(
            session, token, "POST", f"/channels/{welcome_id}/messages", payload
        )
        if status not in (200, 201):
            raise RuntimeError(f"{label}: post failed: {status} {panel}")
        mid = panel["id"]
        await api(session, token, "PUT", f"/channels/{welcome_id}/pins/{mid}")
        print(f"Posted new panel: {mid}")
        return

    for msg in panels:
        mid = msg["id"]
        status, data = await api(
            session, token, "PATCH", f"/channels/{welcome_id}/messages/{mid}", payload
        )
        if status == 200:
            print(f"Updated panel: {mid}")
        else:
            print(f"Failed {mid}: {status} {data}")


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Refresh welcome channel panels")
    parser.add_argument("--guild", choices=("main", "backup", "all"), default="all")
    args = parser.parse_args()

    targets: list[tuple[str, int]] = []
    if args.guild in ("main", "all"):
        targets.append(("ShadowMain", SHADOW_MAIN_GUILD_ID))
    if args.guild in ("backup", "all"):
        targets.append(("ShadowBackup", SHADOW_BACKUP_GUILD_ID))

    token = fetch_shadow_discord_token()

    async with aiohttp.ClientSession() as session:
        status, me = await api(session, token, "GET", "/users/@me")
        print(f"Deploying as {me.get('username')} ({me.get('id')})")

        for label, guild_id in targets:
            await deploy_guild(session, token, label, guild_id)

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
