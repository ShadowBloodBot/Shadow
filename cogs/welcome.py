# cogs/welcome.py — welcome channel info panel

import json
import logging
import os
from pathlib import Path
from typing import Any

import discord
from discord import ButtonStyle
from discord.ui import Button, View
from discord.ext import commands

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    ch_id,
    channel_url,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
)

logger = logging.getLogger("ShadowSyn.Welcome")

THEME_PRIMARY = 0x2B0B35
PANEL_TITLE = "Welcome to ShadowSyn"
VANITY_INVITE_URL = "https://discord.gg/shadowsyn"
MINION_BUTTON_ID = "hub_minion_grab"

_REPO_DATA = Path(__file__).resolve().parents[1] / "data"
_persist_env = os.getenv("PERSIST_PATH", "").strip()
if _persist_env:
    STORE_PATH = Path(_persist_env).resolve() / "welcome_panel.json"
else:
    STORE_PATH = _REPO_DATA / "welcome_panel.json"
_REPO_STORE = _REPO_DATA / "welcome_panel.json"


def _atomic_write(file_path: Path, data: Any) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = file_path.with_suffix(".tmp")
    temp_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp_path.replace(file_path)


async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        if hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception:
        return None


def build_welcome_embed(guild_id: int) -> discord.Embed:
    jtc = ch_id(guild_id, "jtc")
    game_roles = ch_id(guild_id, "game_roles")
    steam = ch_id(guild_id, "steam_codes")
    embed = discord.Embed(title=PANEL_TITLE, color=THEME_PRIMARY)
    embed.add_field(
        name="👻 Getting Started",
        value=(
            f"> Grab your Starter role **[ Minion ]** below so you can see "
            f"<#{game_roles}> & share your <#{steam}>."
        ),
        inline=False,
    )
    embed.add_field(
        name="❓ Support",
        value="Ping @Gravy if you need to vent about how hard your life is.",
        inline=False,
    )
    embed.add_field(
        name="🛠️ Public Features",
        value=(
            "> `/poll` — live button poll with results\n"
            "> `/remindme` — personal reminder (DM or this channel)\n"
            "> `/countdown` — shared event timer with optional role ping"
        ),
        inline=False,
    )
    embed.add_field(
        name="Create Voice Channel",
        value=(
            f"> **Creating your own voice call:** In <#{jtc}> you'll get your own "
            "Control Panel that allows you to control your VC. Locking it from others, "
            "editing the bitrate, user limiting etc if you want a chill chat of just "
            "2 of you it's your choice."
        ),
        inline=False,
    )
    embed.add_field(
        name="\u200b",
        value="---",
        inline=False,
    )
    embed.add_field(
        name="🤖 Member Commands Only",
        value="*Feature List for the ShadowSyn Bot*",
        inline=False,
    )
    embed.add_field(
        name="🍌 Utility & Fun",
        value=(
            "> `/gamble` Play, Win & Redeem\n"
            "> `/speak` TTS bot translate any language\n"
            "> `/haste` Random Haste fact.\n"
            "> `/play` Play any song, Music bot with buttons.\n"
            "> `M!P` Any song search"
        ),
        inline=False,
    )
    embed.add_field(
        name="🔗 Invite",
        value=(
            f"If you like it here, invite people you actually want to play with: "
            f"{VANITY_INVITE_URL} ShadowSyn"
        ),
        inline=False,
    )
    return embed


class WelcomePanelView(View):
    """Static hub buttons — Minion grab handled statelessly in hub.py's on_interaction."""

    def __init__(self, guild_id: int):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.add_item(Button(
            label="Minion",
            style=ButtonStyle.primary,
            emoji="👻",
            custom_id=MINION_BUTTON_ID,
        ))
        self.add_item(Button(
            label="Game-Roles",
            style=ButtonStyle.link,
            emoji="🎮",
            url=channel_url(guild_id, "game_roles"),
        ))
        self.add_item(Button(
            label="Steam-Codes",
            style=ButtonStyle.link,
            emoji="📥",
            url=channel_url(guild_id, "steam_codes"),
        ))
        self.add_item(Button(
            label="Invite Friends",
            style=ButtonStyle.link,
            emoji="🔗",
            url=VANITY_INVITE_URL,
        ))


class WelcomeCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self._store: dict[str, Any] = {}
        self._load_store()

    def _load_store(self) -> dict[str, Any]:
        source = STORE_PATH if STORE_PATH.exists() else _REPO_STORE
        data: dict[str, Any] = {}
        if source.exists():
            try:
                loaded = json.loads(source.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except Exception as exc:
                logger.error("Failed to load welcome_panel.json: %s", exc)
        self._store = data
        return data

    def _save_store(self) -> None:
        _atomic_write(STORE_PATH, self._store)

    def _guild_cfg(self, guild_id: int) -> dict[str, Any]:
        key = str(guild_id)
        if key not in self._store:
            self._store[key] = {"panel_message_id": None}
        return self._store[key]

    async def _find_existing_panel(self, channel: discord.abc.Messageable) -> discord.Message | None:
        if hasattr(channel, "pins"):
            try:
                pins = await channel.pins()
                for msg in pins:
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    if msg.embeds and msg.embeds[0].title == PANEL_TITLE:
                        return msg
            except Exception as exc:
                logger.warning("Could not scan welcome pins: %s", exc)
        try:
            if hasattr(channel, "history"):
                async for msg in channel.history(limit=30):
                    if not msg.author or msg.author.id != self.bot.user.id:
                        continue
                    if msg.embeds and msg.embeds[0].title == PANEL_TITLE:
                        return msg
        except Exception as exc:
            logger.warning("Could not scan welcome history: %s", exc)
        return None

    async def _deploy_panel(self, guild: discord.Guild) -> discord.Message:
        channel = await resolve_channel(self.bot, guild.id, "welcome")
        if channel is None:
            raise RuntimeError("welcome channel not found in registry.")

        cfg = self._guild_cfg(guild.id)
        embed = build_welcome_embed(guild.id)
        view = WelcomePanelView(guild.id)

        existing_id = cfg.get("panel_message_id")
        msg: discord.Message | None = None
        if existing_id:
            try:
                msg = await channel.fetch_message(int(existing_id))
            except Exception:
                msg = None
        if msg is None:
            msg = await self._find_existing_panel(channel)

        if msg is not None:
            await msg.edit(embed=embed, view=view)
        else:
            msg = await channel.send(embed=embed, view=view)
            try:
                await msg.pin()
            except Exception as exc:
                logger.warning("Could not pin welcome panel: %s", exc)

        cfg["panel_message_id"] = str(msg.id)
        self._save_store()
        return msg

    @commands.Cog.listener()
    async def on_ready(self):
        try:
            for gid in REGISTERED_GUILD_IDS:
                self.bot.add_view(WelcomePanelView(gid))
            logger.info("Welcome panel views registered for ShadowMain + ShadowBackup.")
        except Exception as exc:
            logger.error("Failed to register welcome view on_ready: %s", exc)

    @discord.slash_command(
        name="welcome_deploy",
        description="Post or refresh the welcome channel info panel.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def welcome_deploy(self, ctx: discord.ApplicationContext):
        if not ctx.guild or not is_registered_guild(ctx.guild.id):
            return await safe_reply(ctx, "⛔ Unregistered guild.", ephemeral=True)
        if not has_admin_shadow(ctx.author, ctx.guild.id):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        await safe_reply(ctx, "🛠️ Deploying welcome panel...", ephemeral=True)
        try:
            msg = await self._deploy_panel(ctx.guild)
            ch = await resolve_channel(self.bot, ctx.guild.id, "welcome")
            mention = ch.mention if ch else "welcome channel"
            await safe_reply(
                ctx,
                f"✅ Welcome panel live in {mention} · message `{msg.id}`",
                ephemeral=True,
            )
        except Exception as exc:
            logger.error("welcome_deploy failed: %s", exc)
            await safe_reply(ctx, f"❌ Deploy failed: {exc}", ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(WelcomeCog(bot))
