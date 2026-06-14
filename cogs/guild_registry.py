# cogs/guild_registry.py — ShadowMain + ShadowBackup dual-guild configuration

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import discord

logger = logging.getLogger("ShadowSyn.GuildRegistry")

# ── Guild identities (ShadowMain / ShadowBackup) ──
SHADOW_MAIN_GUILD_ID = 908659586536468540
SHADOW_BACKUP_GUILD_ID = 1514838718119411832
REGISTERED_GUILD_IDS = [SHADOW_MAIN_GUILD_ID, SHADOW_BACKUP_GUILD_ID]

# Legacy alias used across cogs during migration
TARGET_GUILD_ID = SHADOW_MAIN_GUILD_ID

OWNER_ID = 482463400929263627

CHANNEL_KEYS = (
    "lobby",
    "general_open",
    "welcome",
    "steam_codes",
    "clips",
    "jtc",
    "casino",
    "arrivals",
    "departures",
    "voice_audit",
    "war",
    "sand_general",
    "arma_stats",
    "steam_action_pvp",
    "steam_adventure_coop",
    "vc_category",
    "tts_history",
)

ROLE_KEYS = ("minion", "member", "admin_shadow")

_SHADOW_MAIN_CHANNELS: dict[str, int] = {
    "lobby": 974113723188912218,
    "general_open": 956725685014134785,
    "welcome": 1166874144395247757,
    "steam_codes": 961870662006345798,
    "clips": 955609588470808657,
    "jtc": 1398618132788281364,
    "casino": 1468766727134249091,
    "arrivals": 959629903186259978,
    "departures": 960088192177029140,
    "voice_audit": 961726632249425930,
    "war": 1475981718904242309,
    "sand_general": 1514542049997623436,
    "arma_stats": 1408314132473843734,
    "steam_action_pvp": 1511889734715310181,
    "steam_adventure_coop": 1511892213775204393,
    "vc_category": 908659586536468542,
    "tts_history": 1400048671973703690,
}

_SHADOW_MAIN_ROLES: dict[str, int] = {
    "minion": 955600021502431233,
    "member": 955600320287887400,
    "admin_shadow": 1214794734770323466,
}

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"
_persist_env = os.getenv("PERSIST_PATH", "").strip()
if _persist_env:
    PERSIST_ROOT = Path(_persist_env).resolve()
else:
    PERSIST_ROOT = _REPO_DATA
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = _REPO_DATA
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)

REGISTRY_PATH = PERSIST_ROOT / "guild_registry.json"
_REPO_REGISTRY = _REPO_DATA / "guild_registry.json"


@dataclass(frozen=True)
class GuildConfig:
    guild_id: int
    channels: dict[str, int]
    roles: dict[str, int]


_registry: dict[str, Any] | None = None


def _atomic_write(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _default_registry() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "primary_guild_id": str(SHADOW_MAIN_GUILD_ID),
        "backup_guild_id": str(SHADOW_BACKUP_GUILD_ID),
        "guilds": {
            str(SHADOW_MAIN_GUILD_ID): {
                "channels": {k: str(v) for k, v in _SHADOW_MAIN_CHANNELS.items()},
                "roles": {k: str(v) for k, v in _SHADOW_MAIN_ROLES.items()},
            },
            str(SHADOW_BACKUP_GUILD_ID): {
                "channels": {},
                "roles": {},
            },
        },
    }


def load_registry(force: bool = False) -> dict[str, Any]:
    global _registry
    if _registry is not None and not force:
        return _registry

    data = _default_registry()
    source_path = REGISTRY_PATH if REGISTRY_PATH.exists() else _REPO_REGISTRY
    if source_path.exists():
        try:
            loaded = json.loads(source_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and isinstance(loaded.get("guilds"), dict):
                data = loaded
        except Exception as exc:
            logger.error(
                "Failed to load guild_registry.json — using embedded ShadowMain defaults: %s",
                exc,
            )

    guilds = data.setdefault("guilds", {})
    main_key = str(SHADOW_MAIN_GUILD_ID)
    backup_key = str(SHADOW_BACKUP_GUILD_ID)
    main_entry = guilds.setdefault(main_key, {"channels": {}, "roles": {}})
    guilds.setdefault(backup_key, {"channels": {}, "roles": {}})
    main_ch = main_entry.setdefault("channels", {})
    main_ro = main_entry.setdefault("roles", {})
    for key, val in _SHADOW_MAIN_CHANNELS.items():
        main_ch.setdefault(key, str(val))
    for key, val in _SHADOW_MAIN_ROLES.items():
        main_ro.setdefault(key, str(val))

    _registry = data
    return data


def save_registry(data: dict[str, Any] | None = None) -> None:
    global _registry
    payload = data if data is not None else load_registry()
    _atomic_write(REGISTRY_PATH, payload)
    _registry = payload


def is_registered_guild(guild_id: int | str | None) -> bool:
    if guild_id is None:
        return False
    try:
        gid = int(guild_id)
    except (TypeError, ValueError):
        return False
    return gid in REGISTERED_GUILD_IDS


def guild_cfg(guild_id: int | str) -> GuildConfig:
    gid = int(guild_id)
    reg = load_registry()
    entry = reg.get("guilds", {}).get(str(gid), {})
    channels: dict[str, int] = {}
    roles: dict[str, int] = {}
    for key, raw in (entry.get("channels") or {}).items():
        try:
            channels[key] = int(raw)
        except (TypeError, ValueError):
            pass
    for key, raw in (entry.get("roles") or {}).items():
        try:
            roles[key] = int(raw)
        except (TypeError, ValueError):
            pass
    if gid == SHADOW_MAIN_GUILD_ID:
        for key, val in _SHADOW_MAIN_CHANNELS.items():
            channels.setdefault(key, val)
        for key, val in _SHADOW_MAIN_ROLES.items():
            roles.setdefault(key, val)
    return GuildConfig(guild_id=gid, channels=channels, roles=roles)


def ch_id(guild_id: int | str, key: str) -> int | None:
    return guild_cfg(guild_id).channels.get(key)


def role_id(guild_id: int | str, key: str) -> int | None:
    return guild_cfg(guild_id).roles.get(key)


def channel_url(guild_id: int | str, key: str) -> str:
    cid = ch_id(guild_id, key)
    gid = int(guild_id)
    if cid is None:
        return f"https://discord.com/channels/{gid}"
    return f"https://discord.com/channels/{gid}/{cid}"


async def resolve_channel(bot: discord.Bot, guild_id: int | str, key: str):
    cid = ch_id(guild_id, key)
    if cid is None:
        return None
    channel = bot.get_channel(cid)
    if channel is not None:
        return channel
    try:
        return await bot.fetch_channel(cid)
    except Exception as exc:
        logger.error("Channel %s (%s) unavailable in guild %s: %s", key, cid, guild_id, exc)
        return None


def resolve_role(guild: discord.Guild, key: str) -> discord.Role | None:
    rid = role_id(guild.id, key)
    if rid is None:
        return None
    return guild.get_role(rid)


def is_owner(user: discord.User | discord.Member | None) -> bool:
    """Joseph (ultimate admin) — bypasses all role and channel gates."""
    if user is None:
        return False
    try:
        return int(user.id) == OWNER_ID
    except (TypeError, ValueError, AttributeError):
        return False


def _guild_id_for_user(
    user: discord.User | discord.Member | None,
    guild_id: int | str | None = None,
) -> int | None:
    if guild_id is not None:
        try:
            return int(guild_id)
        except (TypeError, ValueError):
            return None
    if isinstance(user, discord.Member) and user.guild:
        return user.guild.id
    return None


def has_admin_shadow(
    user: discord.User | discord.Member | None,
    guild_id: int | str | None = None,
) -> bool:
    if is_owner(user):
        return True
    if not isinstance(user, discord.Member):
        return False
    gid = _guild_id_for_user(user, guild_id)
    if gid is None:
        return False
    rid = role_id(gid, "admin_shadow")
    if rid is None:
        return False
    return any(role.id == rid for role in user.roles)


def has_member_role(
    user: discord.User | discord.Member | None,
    guild_id: int | str | None = None,
) -> bool:
    if is_owner(user):
        return True
    if not isinstance(user, discord.Member):
        return False
    gid = _guild_id_for_user(user, guild_id)
    if gid is None:
        return False
    rid = role_id(gid, "member")
    if rid is None:
        return False
    return any(role.id == rid for role in user.roles)


def iter_registered_guild_ids() -> list[int]:
    return list(REGISTERED_GUILD_IDS)


def normalize_channel_name(name: str) -> str:
    if not name:
        return ""
    text = unicodedata.normalize("NFKD", name)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# Back-compat ShadowMain constants
LOBBY_CHANNEL_ID = _SHADOW_MAIN_CHANNELS["lobby"]
GENERAL_OPEN_CHANNEL_ID = _SHADOW_MAIN_CHANNELS["general_open"]
STEAM_CODES_CHANNEL_ID = _SHADOW_MAIN_CHANNELS["steam_codes"]
WELCOME_CHANNEL_ID = _SHADOW_MAIN_CHANNELS["welcome"]
CLIPS_CHANNEL_ID = _SHADOW_MAIN_CHANNELS["clips"]
JTC_CHANNEL_ID = _SHADOW_MAIN_CHANNELS["jtc"]
CASINO_CHANNEL_ID = _SHADOW_MAIN_CHANNELS["casino"]
MINION_ROLE_ID = _SHADOW_MAIN_ROLES["minion"]
MEMBER_ROLE_ID = _SHADOW_MAIN_ROLES["member"]
ROLE_ADMIN_ID = _SHADOW_MAIN_ROLES["admin_shadow"]
GAMBLER_ROLE_ID = _SHADOW_MAIN_ROLES["member"]
