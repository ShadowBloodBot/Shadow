"""ShadowAdmin: bind Steam release genre filters to New Game Releases threads."""

import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]

PERSIST_PATH = os.getenv("PERSIST_PATH", str(ROOT / "data"))
STEAM_STATE_FILE = os.path.join(PERSIST_PATH, "steam_releases.json")
STEAM_TEMP_FILE = os.path.join(PERSIST_PATH, "steam_releases.tmp")

SHADOWSYN_COLOR = 0x2B0B35

THREAD_BINDINGS = {
    "1511889734715310181": "Action, PvP",
    "1511892213775204393": "Adventure, Co-op",
}


def load_state() -> dict:
    if os.path.exists(STEAM_STATE_FILE):
        with open(STEAM_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"targets": {}, "seen_apps": []}


def save_state(data: dict) -> None:
    os.makedirs(PERSIST_PATH, exist_ok=True)
    data["seen_apps"] = data.get("seen_apps", [])[-1000:]
    with open(STEAM_TEMP_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    os.replace(STEAM_TEMP_FILE, STEAM_STATE_FILE)


def binding_embed(channel_id: str, genre_filter: str) -> dict:
    return {
        "embeds": [{
            "title": "Steam Tracker — Thread Bound",
            "description": (
                f"✅ **ShadowAdmin** registered this thread for exclusive Steam new-release routing.\n\n"
                f"🎯 **Filter:** `{genre_filter}`\n"
                f"📌 **Routing:** One release → one best-matching thread (no duplicate cross-posts)."
            ),
            "color": SHADOWSYN_COLOR,
            "footer": {"text": f"Channel {channel_id} | ShadowSyn Network"},
        }]
    }


async def send(session: aiohttp.ClientSession, channel_id: str, payload: dict) -> int:
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with session.post(url, headers=headers, json=payload) as resp:
        text = await resp.text()
        print(f"channel={channel_id} status={resp.status}")
        if resp.status >= 400:
            print(text[:500])
        return resp.status


async def main():
    state = load_state()
    targets = state.get("targets", {})
    if isinstance(targets, list):
        targets = {str(t): None for t in targets}

    for channel_id, genre_filter in THREAD_BINDINGS.items():
        targets[channel_id] = genre_filter

    state["targets"] = targets
    save_state(state)
    print(f"Saved {len(THREAD_BINDINGS)} thread bindings to {STEAM_STATE_FILE}")

    async with aiohttp.ClientSession() as session:
        for channel_id, genre_filter in THREAD_BINDINGS.items():
            await send(session, channel_id, binding_embed(channel_id, genre_filter))


if __name__ == "__main__":
    asyncio.run(main())
