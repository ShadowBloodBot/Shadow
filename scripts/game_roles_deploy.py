"""Rename game-roles channel to Server Info aesthetic and post the hub panel."""

import argparse
import asyncio
import json
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
HEADERS = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}

GAME_ROLES_CHANNEL_ID = "1516222122211672084"
SHADOW_MAIN_GUILD_ID = 908659586536468540
CHANNEL_DISPLAY_NAME = "『🎮』 𝙜𝙖𝙢𝙚-𝙧𝙤𝙡𝙚𝙨"
THEME_PRIMARY = 0x2B0B35
OPEN_BUTTON_ID = f"game_roles_open:{SHADOW_MAIN_GUILD_ID}"


async def api(session, method, path, payload=None):
    async with session.request(
        method,
        f"https://discord.com/api/v10{path}",
        headers=HEADERS,
        json=payload,
    ) as resp:
        text = await resp.text()
        data = json.loads(text) if text else {}
        return resp.status, data


async def rename_channel(session) -> bool:
    status, data = await api(
        session,
        "PATCH",
        f"/channels/{GAME_ROLES_CHANNEL_ID}",
        {"name": CHANNEL_DISPLAY_NAME},
    )
    if status in (200, 201):
        print(f"Channel renamed: {data.get('name')!r}")
        return True
    print(f"Channel rename failed ({status}): {data}")
    return False


async def post_panel(session) -> str | None:
    panel_embed = {
        "title": "🎮 Game Roles",
        "description": (
            "Pick every game you play — your Discord roles **sync instantly**.\n\n"
            "**How it works**\n"
            "1. Click **Choose Games** below\n"
            "2. Select all games you want (pre-filled with your current picks)\n"
            "3. Submit — added and removed automatically\n\n"
            "Staff roles (**Member**, **Silhouette**, **Shadow**, etc.) are assigned "
            "manually by admins and are not listed here."
        ),
        "color": THEME_PRIMARY,
        "footer": {"text": "ShadowSyn • Pick every game you play"},
    }
    components = [{
        "type": 1,
        "components": [{
            "type": 2,
            "style": 1,
            "label": "Choose Games",
            "emoji": {"name": "🎮"},
            "custom_id": OPEN_BUTTON_ID,
        }],
    }]
    status, panel = await api(
        session,
        "POST",
        f"/channels/{GAME_ROLES_CHANNEL_ID}/messages",
        {"embeds": [panel_embed], "components": components},
    )
    if status not in (200, 201):
        print(f"Panel post failed ({status}): {panel}")
        return None
    panel_id = panel["id"]
    print(f"Panel posted: {panel_id}")
    await api(session, "PUT", f"/channels/{GAME_ROLES_CHANNEL_ID}/pins/{panel_id}")
    return panel_id


async def main(rename: bool, panel: bool):
    async with aiohttp.ClientSession() as session:
        status, me = await api(session, "GET", "/users/@me")
        if status != 200:
            raise RuntimeError(f"Auth failed: {me}")
        print(f"Deploying as {me.get('username')} ({me.get('id')})")

        if rename:
            await rename_channel(session)
        if panel:
            await post_panel(session)
        print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Game roles channel deploy (ShadowAdmin)")
    parser.add_argument("--no-rename", action="store_true", help="Skip channel rename")
    parser.add_argument("--no-panel", action="store_true", help="Skip panel post")
    args = parser.parse_args()
    asyncio.run(main(rename=not args.no_rename, panel=not args.no_panel))
