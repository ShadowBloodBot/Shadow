"""Rename game-roles channel (ShadowAdmin) and post hub panel (Shadow bot token)."""

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
ADMIN_TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"

GAME_ROLES_CHANNEL_ID = "1516222122211672084"
SHADOW_MAIN_GUILD_ID = 908659586536468540
CHANNEL_DISPLAY_NAME = "『🎮』 𝙜𝙖𝙢𝙚-𝙧𝙤𝙡𝙚𝙨"
THEME_PRIMARY = 0x2B0B35
OPEN_BUTTON_ID = f"game_roles_manage:{SHADOW_MAIN_GUILD_ID}"
PANEL_PREV_ID = "game_roles_panel_prev"
PANEL_NEXT_ID = "game_roles_panel_next"
PANEL_TITLE = "🎮 Game Roles"


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


def panel_payload(role_count: int = 0) -> dict:
    blurb = (
        "Toggle the games you play — your Discord roles **update instantly**.\n\n"
        "Click **Manage My Games** to add or remove roles. "
        "Browse the full list with **Prev / Next** below.\n\n"
        "Staff roles (**Member**, **Silhouette**, **Shadow**, etc.) are assigned manually."
    )
    games_value = "*Catalog empty — admin runs `/game_roles_seed`.*"
    if role_count:
        games_value = f"**{role_count}** games in catalog · sorted A → Z"
    return {
        "embeds": [{
            "title": PANEL_TITLE,
            "description": blurb,
            "color": THEME_PRIMARY,
            "fields": [
                {"name": "📋 Games", "value": games_value, "inline": False},
                {"name": "\u200b", "value": "**Page 1** of **1**", "inline": False},
            ],
            "footer": {"text": "Sorted A → Z · Click Manage My Games to toggle yours"},
        }],
        "components": [
            {
                "type": 1,
                "components": [{
                    "type": 2,
                    "style": 1,
                    "label": "Manage My Games",
                    "emoji": {"name": "🎮"},
                    "custom_id": OPEN_BUTTON_ID,
                }],
            },
            {
                "type": 1,
                "components": [
                    {"type": 2, "style": 2, "label": "Prev", "emoji": {"name": "◀"}, "custom_id": PANEL_PREV_ID, "disabled": True},
                    {"type": 2, "style": 2, "label": "Next", "emoji": {"name": "▶"}, "custom_id": PANEL_NEXT_ID, "disabled": True},
                ],
            },
        ],
    }


async def rename_channel(session) -> bool:
    status, data = await api(
        session,
        ADMIN_TOKEN,
        "PATCH",
        f"/channels/{GAME_ROLES_CHANNEL_ID}",
        {"name": CHANNEL_DISPLAY_NAME},
    )
    if status in (200, 201):
        print(f"Channel renamed: {data.get('name')!r}")
        return True
    print(f"Channel rename failed ({status}): {data}")
    return False


async def purge_foreign_panels(session, shadow_token: str) -> int:
    """Remove ingest panels posted by the wrong bot (ShadowAdmin)."""
    removed = 0
    status, pins = await api(session, shadow_token, "GET", f"/channels/{GAME_ROLES_CHANNEL_ID}/pins")
    if status == 200 and isinstance(pins, list):
        messages = pins
    else:
        messages = []
    status, history = await api(
        session,
        shadow_token,
        "GET",
        f"/channels/{GAME_ROLES_CHANNEL_ID}/messages?limit=25",
    )
    if status == 200 and isinstance(history, list):
        for msg in history:
            if msg not in messages:
                messages.append(msg)

    for msg in messages:
        embeds = msg.get("embeds") or []
        if not embeds or embeds[0].get("title") != PANEL_TITLE:
            continue
        author = msg.get("author") or {}
        if author.get("id") == "1401788343825727618":
            continue
        mid = msg["id"]
        st, _ = await api(session, shadow_token, "DELETE", f"/channels/{GAME_ROLES_CHANNEL_ID}/messages/{mid}")
        if st in (200, 204):
            removed += 1
            print(f"Removed foreign panel: {mid}")
    return removed


async def post_panel(session, shadow_token: str) -> str | None:
    status, pins = await api(session, shadow_token, "GET", f"/channels/{GAME_ROLES_CHANNEL_ID}/pins")
    if status == 200 and isinstance(pins, list):
        for msg in pins:
            embeds = msg.get("embeds") or []
            author = msg.get("author") or {}
            if embeds and embeds[0].get("title") == PANEL_TITLE and author.get("id") == "1401788343825727618":
                mid = msg["id"]
                st, updated = await api(
                    session,
                    shadow_token,
                    "PATCH",
                    f"/channels/{GAME_ROLES_CHANNEL_ID}/messages/{mid}",
                    panel_payload(),
                )
                if st == 200:
                    print(f"Panel refreshed: {mid}")
                    return mid

    status, panel = await api(
        session,
        shadow_token,
        "POST",
        f"/channels/{GAME_ROLES_CHANNEL_ID}/messages",
        panel_payload(),
    )
    if status not in (200, 201):
        print(f"Panel post failed ({status}): {panel}")
        return None
    panel_id = panel["id"]
    print(f"Panel posted: {panel_id}")
    await api(session, shadow_token, "PUT", f"/channels/{GAME_ROLES_CHANNEL_ID}/pins/{panel_id}")
    return panel_id


async def main(rename: bool, panel: bool):
    railway = railway_token()
    env_id, service_id = resolve_railway_ids(railway)
    shadow_token = fetch_shadow_discord_token(railway, env_id, service_id)

    async with aiohttp.ClientSession() as session:
        status, me = await api(session, shadow_token, "GET", "/users/@me")
        if status != 200:
            raise RuntimeError(f"Shadow bot auth failed: {me}")
        print(f"Shadow bot: {me.get('username')} ({me.get('id')})")

        if rename:
            await rename_channel(session)
        if panel:
            await purge_foreign_panels(session, shadow_token)
            await post_panel(session, shadow_token)
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Game roles channel deploy")
    parser.add_argument("--no-rename", action="store_true", help="Skip channel rename")
    parser.add_argument("--no-panel", action="store_true", help="Skip panel post")
    args = parser.parse_args()
    asyncio.run(main(rename=not args.no_rename, panel=not args.no_panel))
