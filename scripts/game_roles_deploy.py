"""Deploy game-roles channel + panel on ShadowMain and/or ShadowBackup."""

import argparse
import asyncio
import json
import os
import sys
import urllib.request
from pathlib import Path
from typing import Any

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from cogs.game_roles import (  # noqa: E402
    MANAGE_PREFIX,
    PANEL_BLURB,
    PANEL_NEXT_ID,
    PANEL_PREV_ID,
    PANEL_TITLE,
    PAGE_SIZE,
    THEME_PRIMARY,
    _is_denylisted,
)
from cogs.guild_registry import (  # noqa: E402
    REGISTRY_PATH,
    SHADOW_BACKUP_GUILD_ID,
    SHADOW_MAIN_GUILD_ID,
    _REPO_REGISTRY,
    ch_id,
    load_registry,
    normalize_channel_name,
    role_id,
    save_registry,
)

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
ADMIN_TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
ENV_FILE = ROOT / ".env.railway"
PROJECT_ID = "b147a1c2-7073-4ba9-be34-14f30b200bb4"
SERVICE_NAME = "Shadow"
SHADOW_BOT_ID = "1401788343825727618"
CHANNEL_DISPLAY_NAME = "『🎮』 𝙜𝙖𝙢𝙚-𝙧𝙤𝙡𝙚𝙨"

BACKUP_SERVER_INFO_CAT = "1514838718882648120"
BACKUP_WELCOME_CHANNEL = "1514838718882648121"


def railway_token() -> str:
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if line.startswith("RAILWAY_API_TOKEN="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("RAILWAY_API_TOKEN missing (.env.railway)")


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


def _column_block(items: list[dict[str, Any]]) -> str:
    if not items:
        return "—"
    return "\n".join(f"• **{e.get('label', '?')}**" for e in items)


def _panel_embed_dict(catalog: list[dict[str, Any]], page: int = 0) -> dict[str, Any]:
    total = len(catalog)
    total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    page_items = catalog[page * PAGE_SIZE : page * PAGE_SIZE + PAGE_SIZE]
    left_col = page_items[0::2]
    right_col = page_items[1::2]

    embed: dict[str, Any] = {
        "title": PANEL_TITLE,
        "description": PANEL_BLURB,
        "color": THEME_PRIMARY,
        "footer": {"text": "Sorted A → Z · Manage My Games to set yours"},
    }
    if total == 0:
        embed["fields"] = [{
            "name": "📋 Games",
            "value": "*Nothing here yet — check back soon.*",
            "inline": False,
        }]
    else:
        embed["fields"] = [
            {"name": "Games", "value": _column_block(left_col), "inline": True},
            {"name": "\u200b", "value": _column_block(right_col) if right_col else "—", "inline": True},
            {
                "name": "\u200b",
                "value": f"**Page {page + 1}** of **{total_pages}** · **{total}** game{'s' if total != 1 else ''}",
                "inline": False,
            },
        ]
    return embed


def panel_payload(
    guild_id: int,
    *,
    page: int = 0,
    catalog: list[dict[str, Any]] | None = None,
) -> dict:
    catalog = catalog or []
    total_pages = max(1, (len(catalog) + PAGE_SIZE - 1) // PAGE_SIZE)
    embed = _panel_embed_dict(catalog, page)
    return {
        "embeds": [embed],
        "components": [
            {
                "type": 1,
                "components": [{
                    "type": 2,
                    "style": 1,
                    "label": "Manage My Games",
                    "emoji": {"name": "🎮"},
                    "custom_id": f"{MANAGE_PREFIX}{guild_id}",
                }],
            },
            {
                "type": 1,
                "components": [
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Prev",
                        "emoji": {"name": "◀"},
                        "custom_id": PANEL_PREV_ID,
                        "disabled": page <= 0,
                    },
                    {
                        "type": 2,
                        "style": 2,
                        "label": "Next",
                        "emoji": {"name": "▶"},
                        "custom_id": PANEL_NEXT_ID,
                        "disabled": total_pages <= 1 or page >= total_pages - 1,
                    },
                ],
            },
        ],
    }


def _role_entry(role: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(role["id"]),
        "label": role.get("name") or "Role",
        "emoji": None,
        "sort": int(role.get("position", 0)),
    }


async def ensure_game_roles_channel(session, guild_id: int) -> str | None:
    """Create game-roles on Backup if missing; return channel id string."""
    existing = ch_id(guild_id, "game_roles")
    if existing:
        return str(existing)

    if guild_id != SHADOW_BACKUP_GUILD_ID:
        print(f"  No game_roles in registry for guild {guild_id}")
        return None

    status, channels = await api(
        session, ADMIN_TOKEN, "GET", f"/guilds/{guild_id}/channels"
    )
    if status != 200:
        print(f"  Channel list failed: {channels}")
        return None

    for ch in channels:
        if normalize_channel_name(ch.get("name") or "") == "game-roles":
            cid = str(ch["id"])
            print(f"  Found existing backup game-roles: {cid}")
            _register_channel(guild_id, cid)
            return cid

    status, welcome = await api(session, ADMIN_TOKEN, "GET", f"/channels/{BACKUP_WELCOME_CHANNEL}")
    overwrites = welcome.get("permission_overwrites", []) if status == 200 else []

    status, created = await api(
        session,
        ADMIN_TOKEN,
        "POST",
        f"/guilds/{guild_id}/channels",
        {
            "name": CHANNEL_DISPLAY_NAME,
            "type": 0,
            "parent_id": BACKUP_SERVER_INFO_CAT,
            "permission_overwrites": overwrites,
        },
    )
    if status not in (200, 201):
        print(f"  Create channel failed ({status}): {created}")
        return None

    cid = str(created["id"])
    print(f"  Created backup game-roles channel: {cid}")
    _register_channel(guild_id, cid)
    return cid


def _register_channel(guild_id: int, channel_id: str) -> None:
    reg = load_registry(force=True)
    entry = reg.setdefault("guilds", {}).setdefault(str(guild_id), {"channels": {}, "roles": {}})
    entry.setdefault("channels", {})["game_roles"] = channel_id
    save_registry(reg)
    repo = _REPO_REGISTRY
    if repo.exists():
        repo_data = json.loads(repo.read_text(encoding="utf-8"))
        repo_entry = repo_data.setdefault("guilds", {}).setdefault(str(guild_id), {"channels": {}, "roles": {}})
        repo_entry.setdefault("channels", {})["game_roles"] = channel_id
        tmp = repo.with_suffix(".tmp")
        tmp.write_text(json.dumps(repo_data, indent=2), encoding="utf-8")
        tmp.replace(repo)


async def rename_channel_if_main(session, guild_id: int, channel_id: int) -> None:
    if guild_id != SHADOW_MAIN_GUILD_ID:
        return
    status, data = await api(
        session,
        ADMIN_TOKEN,
        "PATCH",
        f"/channels/{channel_id}",
        {"name": CHANNEL_DISPLAY_NAME},
    )
    if status in (200, 201):
        print(f"  Renamed main channel: {data.get('name')!r}")
    else:
        print(f"  Rename warning ({status}): {data}")


async def purge_foreign_panels(session, shadow_token: str, channel_id: int) -> int:
    removed = 0
    messages: list[dict] = []
    for path in (f"/channels/{channel_id}/pins", f"/channels/{channel_id}/messages?limit=25"):
        status, data = await api(session, shadow_token, "GET", path)
        if status == 200 and isinstance(data, list):
            for msg in data:
                if msg not in messages:
                    messages.append(msg)

    for msg in messages:
        embeds = msg.get("embeds") or []
        if not embeds or embeds[0].get("title") != PANEL_TITLE:
            continue
        if (msg.get("author") or {}).get("id") == SHADOW_BOT_ID:
            continue
        mid = msg["id"]
        st, _ = await api(session, shadow_token, "DELETE", f"/channels/{channel_id}/messages/{mid}")
        if st in (200, 204):
            removed += 1
    return removed


async def post_panel(
    session,
    shadow_token: str,
    guild_id: int,
    channel_id: int,
    catalog: list[dict[str, Any]] | None = None,
) -> str | None:
    payload = panel_payload(guild_id, catalog=catalog)

    status, pins = await api(session, shadow_token, "GET", f"/channels/{channel_id}/pins")
    if status == 200 and isinstance(pins, list):
        for msg in pins:
            embeds = msg.get("embeds") or []
            author = msg.get("author") or {}
            if embeds and embeds[0].get("title") == PANEL_TITLE and author.get("id") == SHADOW_BOT_ID:
                mid = msg["id"]
                st, _ = await api(
                    session,
                    shadow_token,
                    "PATCH",
                    f"/channels/{channel_id}/messages/{mid}",
                    payload,
                )
                if st == 200:
                    print(f"  Panel refreshed: {mid}")
                    return mid

    status, panel = await api(
        session,
        shadow_token,
        "POST",
        f"/channels/{channel_id}/messages",
        payload,
    )
    if status not in (200, 201):
        print(f"  Panel post failed ({status}): {panel}")
        return None
    panel_id = panel["id"]
    print(f"  Panel posted: {panel_id}")
    await api(session, shadow_token, "PUT", f"/channels/{channel_id}/pins/{panel_id}")
    return panel_id


async def seed_catalog_preview(session, guild_id: int) -> list[dict[str, Any]]:
    """Build catalog entries for repo seed file (mirrors /game_roles_seed)."""
    status, roles = await api(session, ADMIN_TOKEN, "GET", f"/guilds/{guild_id}/roles")
    if status != 200 or not isinstance(roles, list):
        return []

    minion_rid = role_id(guild_id, "minion")
    minion_pos = 61
    if minion_rid:
        for role in roles:
            if str(role.get("id")) == str(minion_rid):
                minion_pos = int(role.get("position", 61))
                break

    class _FakeGuild:
        def __init__(self, gid: int, role_list: list[dict]):
            self.id = gid
            self._roles = role_list

        def get_role(self, rid: int):
            for r in self._roles:
                if int(r["id"]) == rid:
                    return _FakeRole(r, self)
            return None

    class _FakeRole:
        def __init__(self, data: dict, guild: _FakeGuild):
            self.id = int(data["id"])
            self.name = data.get("name") or ""
            self.position = int(data.get("position", 0))
            self.managed = bool(data.get("managed", False))
            self.guild = guild

        def is_default(self) -> bool:
            return self.name == "@everyone"

    fake_guild = _FakeGuild(guild_id, roles)
    entries: list[dict[str, Any]] = []
    for role in sorted(roles, key=lambda r: -int(r.get("position", 0))):
        fake = _FakeRole(role, fake_guild)
        if fake.position >= minion_pos:
            continue
        if _is_denylisted(fake, guild_id):
            continue
        entries.append(_role_entry(role))

    return sorted(entries, key=lambda e: str(e.get("label") or "").lower())


def _normalize_role_name(name: str) -> str:
    return (name or "").strip().lower()


def update_game_roles_store(guild_id: int, channel_id: str, panel_id: str | None, roles: list[dict]) -> None:
    store_path = ROOT / "data" / "game_roles.json"
    data: dict[str, Any] = {}
    if store_path.exists():
        try:
            data = json.loads(store_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[str(guild_id)] = {
        "channel_id": channel_id,
        "panel_message_id": panel_id,
        "panel_page": 0,
        "roles": roles,
    }
    tmp = store_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(store_path)


async def deploy_guild(
    session,
    shadow_token: str,
    label: str,
    guild_id: int,
    *,
    rename: bool,
    panel: bool,
    seed: bool,
) -> None:
    print(f"\n=== {label} ({guild_id}) ===")
    cid = await ensure_game_roles_channel(session, guild_id)
    if not cid:
        cid = ch_id(guild_id, "game_roles")
    if not cid:
        print("  SKIP — no game_roles channel")
        return
    cid = int(cid)

    if rename:
        await rename_channel_if_main(session, guild_id, cid)

    panel_id = None
    roles: list[dict] = []
    if seed:
        roles = await seed_catalog_preview(session, guild_id)
        print(f"  Catalog seed preview: {len(roles)} roles")

    if panel:
        removed = await purge_foreign_panels(session, shadow_token, cid)
        if removed:
            print(f"  Purged {removed} foreign panel(s)")
        panel_id = await post_panel(session, shadow_token, guild_id, cid, roles or None)

    if seed:
        update_game_roles_store(guild_id, str(cid), panel_id, roles)


async def main():
    parser = argparse.ArgumentParser(description="Deploy game roles hub (dual guild)")
    parser.add_argument("--guild", choices=("main", "backup", "all"), default="all")
    parser.add_argument("--no-rename", action="store_true")
    parser.add_argument("--no-panel", action="store_true")
    parser.add_argument("--seed", action="store_true", help="Update data/game_roles.json catalog preview")
    args = parser.parse_args()

    load_registry(force=True)
    shadow_token = fetch_shadow_discord_token()

    targets: list[tuple[str, int]] = []
    if args.guild in ("main", "all"):
        targets.append(("ShadowMain", SHADOW_MAIN_GUILD_ID))
    if args.guild in ("backup", "all"):
        targets.append(("ShadowBackup", SHADOW_BACKUP_GUILD_ID))

    async with aiohttp.ClientSession() as session:
        status, me = await api(session, shadow_token, "GET", "/users/@me")
        if status != 200:
            raise RuntimeError(f"Shadow bot auth failed: {me}")
        print(f"Shadow bot: {me.get('username')} ({me.get('id')})")

        for label, gid in targets:
            await deploy_guild(
                session,
                shadow_token,
                label,
                gid,
                rename=not args.no_rename,
                panel=not args.no_panel,
                seed=args.seed,
            )

    print("\nDone.")
    print("Run /game_roles_seed in each guild on production to sync Railway /data catalog.")


if __name__ == "__main__":
    asyncio.run(main())
