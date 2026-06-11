# cogs/steam_codes.py
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import ButtonStyle, Interaction
from discord.ui import View, Button, Modal, TextInput
from discord.ext import commands

# ==============================================================================
# TELEMETRY
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [ShadowSyn] %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("ShadowSyn.SteamCodes")

# ==============================================================================
# CONSTANTS & IDS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
ROLE_ADMIN_ID = 1214794734770323466
TARGET_GUILD_ID = 908659586536468540

STEAM_CODES_CHANNEL_ID = 961870662006345798

PAGE_SIZE = 10

ADD_BUTTON_ID = "steam_codes_add"
PREV_BUTTON_ID = "steam_codes_prev"
NEXT_BUTTON_ID = "steam_codes_next"

STEAM_CODE_RE = re.compile(r"^\d{6,12}$")
STEAM_CODE_FIND_RE = re.compile(r"\b(\d{6,12})\b")
STEAM_PROFILE_RE = re.compile(
    r"steamcommunity\.com/profiles/(\d{17})",
    re.I,
)

PANEL_TITLE = "🎮 Steam Friend Codes"
PANEL_BLURB = (
    "Add your **Steam friend code** so guildmates can find you in-game.\n"
    "You can register **multiple codes** (mains, alts, smurfs).\n\n"
    "Click **Add Steam Code** below — the directory sorts alphabetically."
)

# ==============================================================================
# PERSISTENCE
# ==============================================================================
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

STORE_PATH = PERSIST_ROOT / "steam_codes.json"


def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"Persistence error [{file_path.name}]: {e}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# HELPERS
# ==============================================================================
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


def _normalize_code(raw: str) -> str | None:
    raw = raw.strip()
    if STEAM_CODE_RE.match(raw):
        return raw
    m = STEAM_PROFILE_RE.search(raw)
    if m:
        steam64 = int(m.group(1))
        friend_code = steam64 - 76561197960265728
        if friend_code > 0:
            return str(friend_code)
    return None


def _display_name(user: discord.User | discord.Member) -> str:
    return getattr(user, "global_name", None) or user.name


def _sorted_entries(entries: list[dict]) -> list[dict]:
    return sorted(
        entries,
        key=lambda e: (e.get("display_name", "").lower(), e.get("code", "")),
    )


def _dedupe_key(entry: dict) -> tuple:
    return (str(entry.get("user_id")), str(entry.get("code")))


# ==============================================================================
# UI COMPONENTS
# ==============================================================================
class SteamCodesPanelView(View):
    """Persistent hub panel — interactions handled in on_interaction."""

    def __init__(self, page: int = 0, total_pages: int = 1):
        super().__init__(timeout=None)
        self.add_item(Button(
            label="Add Steam Code",
            style=ButtonStyle.primary,
            emoji="➕",
            custom_id=ADD_BUTTON_ID,
            row=0,
        ))
        self.add_item(Button(
            label="Prev",
            style=ButtonStyle.secondary,
            emoji="◀",
            custom_id=PREV_BUTTON_ID,
            disabled=page <= 0,
            row=1,
        ))
        self.add_item(Button(
            label="Next",
            style=ButtonStyle.secondary,
            emoji="▶",
            custom_id=NEXT_BUTTON_ID,
            disabled=total_pages <= 1 or page >= total_pages - 1,
            row=1,
        ))


class AddSteamCodeModal(Modal):
    def __init__(self, cog: "SteamCodesCog"):
        super().__init__(title="Add Steam Friend Code")
        self.cog = cog
        self.add_item(TextInput(
            label="Steam Friend Code",
            placeholder="e.g. 35988028  (6–12 digits)",
            style=discord.InputTextStyle.short,
            required=True,
            max_length=80,
        ))

    async def callback(self, interaction: Interaction):
        raw = self.children[0].value.strip()
        code = _normalize_code(raw)
        if not code:
            return await safe_reply(
                interaction,
                "❌ Enter a valid **Steam friend code** (6–12 digits).",
                ephemeral=True,
            )

        user = interaction.user
        name = _display_name(user)
        entries = self.cog.data.setdefault("entries", [])

        if any(
            str(e.get("user_id")) == str(user.id) and str(e.get("code")) == code
            for e in entries
        ):
            return await safe_reply(
                interaction,
                f"ℹ️ You already have `{code}` on the list.",
                ephemeral=True,
            )

        entries.append({
            "user_id": str(user.id),
            "display_name": name,
            "code": code,
            "added_at": _utc_now(),
        })
        for entry in entries:
            if str(entry.get("user_id")) == str(user.id):
                entry["display_name"] = name
        self.cog._save()

        await safe_reply(
            interaction,
            f"✅ Added **`{code}`** for **{name}**.",
            ephemeral=True,
        )
        target_page = self.cog._page_for_code(code)
        await self.cog._refresh_panel_message(interaction.channel, page=target_page)


# ==============================================================================
# CORE COG
# ==============================================================================
class SteamCodesCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.data: dict = {"panel_message_id": None, "current_page": 0, "entries": []}
        self._load_data()

    # --------------------------------------------------------------------------
    # PERSISTENCE
    # --------------------------------------------------------------------------
    def _load_data(self):
        if STORE_PATH.exists():
            try:
                loaded = json.loads(STORE_PATH.read_text(encoding="utf-8"))
                self.data["panel_message_id"] = loaded.get("panel_message_id")
                self.data["current_page"] = loaded.get("current_page", 0)
                self.data["entries"] = loaded.get("entries", []) or []
                logger.info(f"Loaded {len(self.data['entries'])} steam code entries.")
            except Exception as e:
                logger.error(f"Corruption in {STORE_PATH.name}, starting fresh: {e}")
                self.data = {"panel_message_id": None, "current_page": 0, "entries": []}
        else:
            logger.info("No steam codes store found. Initializing empty state.")

    def _save(self):
        _atomic_write(STORE_PATH, self.data)

    # --------------------------------------------------------------------------
    # CHANNEL
    # --------------------------------------------------------------------------
    async def _codes_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(STEAM_CODES_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(STEAM_CODES_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Steam codes channel unavailable: {e}")
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    # --------------------------------------------------------------------------
    # EMBED BUILD
    # --------------------------------------------------------------------------
    def _page_count(self) -> int:
        entries = self.data.get("entries", [])
        if not entries:
            return 1
        return max(1, (len(entries) + PAGE_SIZE - 1) // PAGE_SIZE)

    def _clamp_page(self, page: int) -> int:
        return max(0, min(page, self._page_count() - 1))

    def _page_slice(self, page: int) -> list[dict]:
        entries = _sorted_entries(self.data.get("entries", []))
        start = page * PAGE_SIZE
        return entries[start:start + PAGE_SIZE]

    def _page_for_code(self, code: str) -> int:
        entries = _sorted_entries(self.data.get("entries", []))
        for idx, entry in enumerate(entries):
            if str(entry.get("code")) == str(code):
                return idx // PAGE_SIZE
        return self._clamp_page(self.data.get("current_page", 0))

    def _column_block(self, items: list[dict]) -> str:
        if not items:
            return "—"
        lines = []
        for entry in items:
            name = entry.get("display_name") or "Unknown"
            code = entry.get("code") or "?"
            lines.append(f"**{name}**\n`{code}`")
        return "\n\n".join(lines)

    def build_panel_embed(self, page: int | None = None) -> discord.Embed:
        if page is None:
            page = self.data.get("current_page", 0)
        page = self._clamp_page(page)

        entries = self.data.get("entries", [])
        total = len(entries)
        total_pages = self._page_count()
        page_items = self._page_slice(page)

        left_col = page_items[0::2]
        right_col = page_items[1::2]
        unique_members = len({e.get("user_id") for e in entries})

        embed = discord.Embed(
            title=PANEL_TITLE,
            description=PANEL_BLURB,
            color=THEME_PRIMARY,
        )
        embed.set_thumbnail(
            url="https://upload.wikimedia.org/wikipedia/commons/thumb/8/83/Steam_icon_logo.svg/240px-Steam_icon_logo.svg.png"
        )

        if total == 0:
            embed.add_field(
                name="📋 Directory",
                value="*No codes yet — be the first to add yours.*",
                inline=False,
            )
        else:
            embed.add_field(
                name="Members",
                value=self._column_block(left_col),
                inline=True,
            )
            embed.add_field(
                name="\u200b",
                value=self._column_block(right_col) if right_col else "—",
                inline=True,
            )
            embed.add_field(
                name="\u200b",
                value=(
                    f"**Page {page + 1}** of **{total_pages}** · "
                    f"{total} code{'s' if total != 1 else ''} · "
                    f"{unique_members} member{'s' if unique_members != 1 else ''}"
                ),
                inline=False,
            )

        embed.set_footer(text="Sorted A → Z · Multiple codes per member allowed")
        return embed

    # --------------------------------------------------------------------------
    # PANEL MESSAGE
    # --------------------------------------------------------------------------
    async def _refresh_panel_message(
        self,
        channel: discord.abc.Messageable | None = None,
        *,
        page: int | None = None,
    ):
        if page is not None:
            self.data["current_page"] = self._clamp_page(page)
        else:
            self.data["current_page"] = self._clamp_page(self.data.get("current_page", 0))

        panel_id = self.data.get("panel_message_id")
        if not panel_id:
            return

        if channel is None:
            channel = await self._codes_channel()
        if channel is None:
            return

        page_num = self.data["current_page"]
        total_pages = self._page_count()
        view = SteamCodesPanelView(page_num, total_pages)
        embed = self.build_panel_embed(page_num)

        try:
            msg = await channel.fetch_message(int(panel_id))
            await msg.edit(embed=embed, view=view)
            self.bot.add_view(view)
            self._save()
        except discord.NotFound:
            logger.warning(f"Panel message {panel_id} not found.")
        except Exception as e:
            logger.error(f"Failed to refresh steam codes panel: {e}")

    async def _deploy_panel(self, channel: discord.TextChannel):
        page = self._clamp_page(self.data.get("current_page", 0))
        total_pages = self._page_count()
        view = SteamCodesPanelView(page, total_pages)
        embed = self.build_panel_embed(page)

        panel_msg = await channel.send(embed=embed, view=view)
        self.bot.add_view(view)
        self.data["panel_message_id"] = panel_msg.id
        self.data["current_page"] = page
        self._save()
        logger.info(f"Steam codes panel deployed ({panel_msg.id}).")

    # --------------------------------------------------------------------------
    # PERSISTENT VIEWS
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.bot.add_view(SteamCodesPanelView(0, max(1, self._page_count())))
            logger.info("Steam codes persistent view restored.")
        except Exception as e:
            logger.error(f"Failed to restore steam codes view on_ready: {e}")

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""

        if custom_id == ADD_BUTTON_ID:
            try:
                await interaction.response.send_modal(AddSteamCodeModal(self))
            except Exception as e:
                logger.error(f"Steam code modal failed: {e}")
            return

        if custom_id == PREV_BUTTON_ID:
            new_page = self._clamp_page(self.data.get("current_page", 0) - 1)
            try:
                await interaction.response.defer()
                self.data["current_page"] = new_page
                await self._refresh_panel_message(interaction.channel, page=new_page)
            except Exception as e:
                logger.error(f"Steam codes prev page failed: {e}")
            return

        if custom_id == NEXT_BUTTON_ID:
            new_page = self._clamp_page(self.data.get("current_page", 0) + 1)
            try:
                await interaction.response.defer()
                self.data["current_page"] = new_page
                await self._refresh_panel_message(interaction.channel, page=new_page)
            except Exception as e:
                logger.error(f"Steam codes next page failed: {e}")

    # --------------------------------------------------------------------------
    # IMPORT & WIPE
    # --------------------------------------------------------------------------
    def _import_from_messages(self, messages: list[discord.Message]) -> int:
        entries = self.data.setdefault("entries", [])
        existing = {_dedupe_key(e) for e in entries}
        added = 0

        for msg in messages:
            if msg.author.bot:
                continue
            author = msg.author
            name = _display_name(author)
            uid = str(author.id)
            content = (msg.content or "").strip()

            codes: list[str] = []
            for match in STEAM_CODE_FIND_RE.findall(content):
                if STEAM_CODE_RE.match(match):
                    codes.append(match)

            profile_code = _normalize_code(content)
            if profile_code and profile_code not in codes:
                codes.append(profile_code)

            if not codes and content.isdigit() and STEAM_CODE_RE.match(content):
                codes.append(content)

            for code in codes:
                entry = {
                    "user_id": uid,
                    "display_name": name,
                    "code": code,
                    "added_at": _utc_now(),
                }
                key = _dedupe_key(entry)
                if key in existing:
                    continue
                entries.append(entry)
                existing.add(key)
                added += 1

        if added:
            self._save()
        return added

    async def _purge_channel(self, channel: discord.TextChannel) -> int:
        deleted = 0
        try:
            async for msg in channel.history(limit=None):
                try:
                    await msg.delete()
                    deleted += 1
                except Exception as e:
                    logger.warning(f"Could not delete message {msg.id}: {e}")
        except Exception as e:
            logger.error(f"Channel purge failed: {e}")
        return deleted

    async def _lock_channel_permissions(self, channel: discord.TextChannel):
        guild = channel.guild
        if guild is None:
            return False, "Channel has no guild context."

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return False, "Bot lacks **Manage Channels**."

        reason = "ShadowSyn steam codes: directory is panel-only (use Add Steam Code)"
        skip_ids: set[int] = {me.id}
        if me.top_role:
            skip_ids.add(me.top_role.id)

        targets: list[discord.Role | discord.Member] = [guild.default_role]
        for target in channel.overwrites:
            if target.id in skip_ids or target in targets:
                continue
            targets.append(target)

        updated = 0
        try:
            for target in targets:
                if getattr(target, "id", None) in skip_ids:
                    continue
                ow = channel.overwrites_for(target)
                ow.send_messages = False
                ow.create_public_threads = False
                ow.create_private_threads = False
                await channel.set_permissions(target, overwrite=ow, reason=reason)
                updated += 1
            return True, f"Messaging locked for **{updated}** permission target(s)."
        except discord.Forbidden:
            return False, "Forbidden — check bot **Manage Channels** and role hierarchy."
        except Exception as e:
            return False, str(e)

    # --------------------------------------------------------------------------
    # ADMIN DEPLOY
    # --------------------------------------------------------------------------
    @discord.slash_command(
        name="steam_codes_deploy",
        description="Import existing posts, wipe channel, deploy the Steam codes hub.",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True),
    )
    @commands.has_role(ROLE_ADMIN_ID)
    async def steam_codes_deploy(
        self,
        ctx: discord.ApplicationContext,
        import_history: discord.Option(
            bool,
            description="Scrape existing channel messages into the directory first",
            default=True,
        ),
    ):
        await safe_reply(ctx, "🛠️ Deploying Steam codes hub...", ephemeral=True)

        channel = await self._codes_channel()
        if channel is None:
            return await safe_reply(ctx, "❌ Steam codes channel unavailable.", ephemeral=True)

        imported = 0
        if import_history:
            try:
                messages = [msg async for msg in channel.history(limit=None)]
                imported = self._import_from_messages(messages)
            except Exception as e:
                logger.error(f"Steam codes import failed: {e}")
                return await safe_reply(ctx, f"❌ Import failed: {e}", ephemeral=True)

        perm_ok, perm_status = await self._lock_channel_permissions(channel)
        if not perm_ok:
            return await safe_reply(ctx, f"❌ Could not lock channel: {perm_status}", ephemeral=True)

        purged = await self._purge_channel(channel)

        old_panel_id = self.data.get("panel_message_id")
        self.data["panel_message_id"] = None

        try:
            await self._deploy_panel(channel)
        except Exception as e:
            logger.error(f"Steam codes panel deploy failed: {e}")
            self.data["panel_message_id"] = old_panel_id
            return await safe_reply(ctx, f"❌ Panel deploy failed: {e}", ephemeral=True)

        total = len(self.data.get("entries", []))
        await safe_reply(
            ctx,
            f"✅ Steam codes hub live in {channel.mention}.\n"
            f"• Imported **{imported}** code(s) from history\n"
            f"• Purged **{purged}** old message(s)\n"
            f"• {perm_status}\n"
            f"• **{total}** total entries · Panel `{self.data['panel_message_id']}`",
            ephemeral=True,
        )

    @steam_codes_deploy.error
    async def steam_codes_deploy_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, (commands.MissingRole, commands.CheckFailure)):
            await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)
        else:
            logger.error(f"steam_codes_deploy error: {error}")
            await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(SteamCodesCog(bot))
