# cogs/clips.py
import os
import re
import json
import asyncio
import logging
from pathlib import Path
from urllib.parse import quote

import aiohttp
import discord
from discord import Interaction, ButtonStyle, SelectOption
from discord.ui import View, Button, Select, Modal, TextInput
from discord.ext import commands

# ==============================================================================
# TELEMETRY
# ==============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | [ShadowSyn] %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("ShadowSyn.Clips")

# ==============================================================================
# CONSTANTS & IDS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
THEME_GOLD = 0xFFD700
OWNER_ID = 482463400929263627
ROLE_ADMIN_ID = 1214794734770323466
TARGET_GUILD_ID = 908659586536468540

CLIPS_CHANNEL_ID = 955609588470808657
HOF_VOTE_THRESHOLD = 5

# Optional dedicated read-only Hall of Fame channel. Falls back to hof_thread_id.
try:
    CLIPS_HOF_CHANNEL_ID = int(os.getenv("CLIPS_HOF_CHANNEL_ID", "0")) or None
except (TypeError, ValueError):
    CLIPS_HOF_CHANNEL_ID = None

# Optional developer key for the official Medal search API as a last-resort fallback.
MEDAL_API_KEY = os.getenv("MEDAL_API_KEY")

# Game taxonomy: (label, emoji) — drives both the Select menu and embed title prefix.
CLIP_CATEGORIES = [
    ("PvP/Combat", "💥"),
    ("Funny/Misc", "😂"),
    ("Other", "🎬"),
]
CATEGORY_EMOJI = {label: emoji for label, emoji in CLIP_CATEGORIES}

UA_HEADERS = {"User-Agent": "ShadowSyn/1.0 (+https://medal.tv)"}

MEDAL_URL_RE = re.compile(r"^https?://(?:www\.)?medal\.tv/[^\s]+$", re.I)
MEDAL_CLIP_PATH_RE = re.compile(
    r"(?:"
    r"clip/\d+(?:/[\w-]+)?"
    r"|clips/\d+(?:/[\w-]+)?"
    r"|games/[\w-]+/clips?/\d+(?:/[\w-]+)?"
    r")",
    re.I,
)
YOUTUBE_URL_RE = re.compile(
    r"^https?://(?:www\.)?(?:youtube\.com/watch\?v=[\w-]{11}(?:&[^\s]*)?"
    r"|youtu\.be/[\w-]{11}(?:\?[^\s]*)?"
    r"|youtube\.com/shorts/[\w-]{11}(?:\?[^\s]*)?)$",
    re.I,
)
YOUTUBE_ID_RE = re.compile(
    r"(?:v=|youtu\.be/|shorts/)([\w-]{11})",
    re.I,
)
UPLOAD_FALLBACK_BYTES = 25 * 1024 * 1024
UPLOAD_VIDEO_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-msvideo",
    "video/x-matroska",
}
GENERIC_MEDAL_TITLE_MARKERS = (
    "record, edit, and share",
    "medal is the best way to record",
    "download medal today",
)

# ==============================================================================
# PERSISTENCE
# ==============================================================================
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception:
    PERSIST_ROOT = Path(".").resolve()

CLIPS_STORE = (PERSIST_ROOT / "clips_repo.json")


def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"⚠️ Persistence Error [{file_path.name}]: {e}")


# ==============================================================================
# HELPERS
# ==============================================================================
async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            else:
                return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception:
        return None


def _is_valid_medal_url(url: str) -> bool:
    if not url:
        return False
    url = url.strip()
    if not MEDAL_URL_RE.match(url):
        return False
    path = url.split("medal.tv/", 1)[-1].split("?")[0].strip("/")
    if not path:
        return False
    return bool(MEDAL_CLIP_PATH_RE.search(url))


def _is_valid_youtube_url(url: str) -> bool:
    if not url:
        return False
    return bool(YOUTUBE_URL_RE.match(url.strip()))


def _is_valid_clip_url(url: str) -> bool:
    return _is_valid_medal_url(url) or _is_valid_youtube_url(url)


def _youtube_id(url: str) -> str | None:
    m = YOUTUBE_ID_RE.search(url)
    return m.group(1) if m else None


def _format_mb(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    return str(int(mb)) if mb == int(mb) else f"{mb:.1f}"


def _extract_og(html: str, prop: str):
    patterns = [
        rf'property="{prop}"[^>]+content="([^"]+)"',
        rf'content="([^"]+)"[^>]+property="{prop}"',
        rf"property='{prop}'[^>]+content='([^']+)'",
        rf'name="{prop}"[^>]+content="([^"]+)"',
    ]
    for pat in patterns:
        m = re.search(pat, html, re.I)
        if m:
            return m.group(1).strip()
    return None


# ==============================================================================
# UI COMPONENTS
# ==============================================================================
class SubmitClipPanelView(View):
    """Persistent ingest panel. Logic handled statelessly in on_interaction."""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(
            label="Submit Clip",
            style=ButtonStyle.primary,
            emoji="🎬",
            custom_id="clips_submit_panel",
        ))


class ClipCategorySelect(Select):
    """Ephemeral step 1: pick a category before link modal or file upload."""
    def __init__(self, cog):
        self.cog = cog
        options = [SelectOption(label=label, value=label, emoji=emoji) for label, emoji in CLIP_CATEGORIES]
        super().__init__(placeholder="Select a category for your clip...", options=options, min_values=1, max_values=1)

    async def callback(self, interaction: Interaction):
        category = self.values[0]
        await interaction.response.send_message(
            f"**{category}** — how are you submitting?",
            view=ClipSourceView(self.cog, category),
            ephemeral=True,
        )


class ClipCategoryView(View):
    def __init__(self, cog):
        super().__init__(timeout=180)
        self.add_item(ClipCategorySelect(cog))


class ClipLinkButton(Button):
    def __init__(self, cog, category: str):
        super().__init__(label="Paste Link", style=ButtonStyle.primary, emoji="🔗")
        self.cog = cog
        self.category = category

    async def callback(self, interaction: Interaction):
        await interaction.response.send_modal(ClipUrlModal(self.cog, self.category))


class ClipUploadButton(Button):
    def __init__(self, cog, category: str):
        super().__init__(label="Upload from PC", style=ButtonStyle.secondary, emoji="📁")
        self.cog = cog
        self.category = category

    async def callback(self, interaction: Interaction):
        self.cog._pending_uploads[interaction.user.id] = self.category
        guild = interaction.guild or await self.cog._resolve_guild()
        max_bytes = self.cog._upload_limit_bytes(guild)
        try:
            dm = await interaction.user.create_dm()
            await dm.send(
                f"**Clip upload — {self.category}**\n\n"
                "Reply here with your video file (`mp4`, `webm`, `mov`).\n"
                f"Max size: **{_format_mb(max_bytes)}MB** (this server's Discord limit). "
                "One file per message."
            )
            await interaction.response.send_message(
                "📬 Check your **DMs** — send the video file to Shadow there.",
                ephemeral=True,
            )
        except discord.Forbidden:
            self.cog._pending_uploads.pop(interaction.user.id, None)
            await interaction.response.send_message(
                "❌ I can't DM you. Enable **Server DMs** (Privacy → allow DMs from server members) and try again.",
                ephemeral=True,
            )
        except Exception as e:
            self.cog._pending_uploads.pop(interaction.user.id, None)
            logger.error(f"Failed to open upload DM for {interaction.user.id}: {e}")
            await interaction.response.send_message("❌ Could not open upload DM. Try again.", ephemeral=True)


class ClipSourceView(View):
    def __init__(self, cog, category: str):
        super().__init__(timeout=180)
        self.add_item(ClipLinkButton(cog, category))
        self.add_item(ClipUploadButton(cog, category))


class ClipUrlModal(Modal):
    """Ephemeral step: Medal.tv or YouTube URL."""
    def __init__(self, cog, category: str):
        super().__init__(title="Submit a Clip Link")
        self.cog = cog
        self.category = category
        self.add_item(TextInput(
            label="Medal.tv or YouTube URL",
            placeholder="https://medal.tv/... or https://youtube.com/watch?v=...",
            style=discord.InputTextStyle.short,
            required=True,
            max_length=400,
        ))

    async def callback(self, interaction: Interaction):
        url = self.children[0].value.strip()
        if not _is_valid_clip_url(url):
            return await safe_reply(
                interaction,
                "❌ Paste a valid **Medal.tv** or **YouTube** clip link.",
                ephemeral=True,
            )
        await interaction.response.defer(ephemeral=True)
        await self.cog.publish_clip(interaction, url, self.category)


class ClipVoteView(View):
    """Persistent 🔥 vote view. Logic handled statelessly in on_interaction."""
    def __init__(self, message_id: int, count: int = 0):
        super().__init__(timeout=None)
        label = f"🔥 {count}" if count else "🔥 Vote"
        self.add_item(Button(
            label=label,
            style=ButtonStyle.primary,
            custom_id=f"clip_fire_{message_id}",
        ))


# ==============================================================================
# CORE COG
# ==============================================================================
class ClipsCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.session = None
        self.data = {"panel_message_id": None, "hof_thread_id": None, "clips": {}}
        self._pending_uploads: dict[int, str] = {}
        self._load_data()

    def cog_unload(self):
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())
        logger.info("ClipsCog unloaded. aiohttp session scheduled for closure.")

    # --------------------------------------------------------------------------
    # PERSISTENCE LAYER
    # --------------------------------------------------------------------------
    def _load_data(self):
        if CLIPS_STORE.exists():
            try:
                loaded = json.loads(CLIPS_STORE.read_text(encoding="utf-8"))
                self.data["panel_message_id"] = loaded.get("panel_message_id")
                self.data["hof_thread_id"] = loaded.get("hof_thread_id")
                self.data["clips"] = loaded.get("clips", {}) or {}
                logger.info(f"Loaded {len(self.data['clips'])} tracked clips from repo.")
            except Exception as e:
                logger.error(f"Corruption in {CLIPS_STORE.name}, starting fresh. Error: {e}")
                self.data = {"panel_message_id": None, "hof_thread_id": None, "clips": {}}
        else:
            logger.info("No existing clips repo found. Initializing empty state.")

    def _save(self):
        _atomic_write(CLIPS_STORE, self.data)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _upload_limit_bytes(self, guild: discord.Guild | None) -> int:
        """Discord server cap from boost tier (25 / 50 / 100 MB)."""
        if guild is not None and getattr(guild, "filesize_limit", None):
            return guild.filesize_limit
        return UPLOAD_FALLBACK_BYTES

    async def _resolve_guild(self) -> discord.Guild | None:
        guild = self.bot.get_guild(TARGET_GUILD_ID)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(TARGET_GUILD_ID)
            except Exception as e:
                logger.warning(f"Could not fetch guild for upload limit: {e}")
        return guild

    # --------------------------------------------------------------------------
    # PERSISTENT VIEW RESTORATION
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.bot.add_view(SubmitClipPanelView())
            restored = 0
            for mid, info in self.data.get("clips", {}).items():
                try:
                    self.bot.add_view(ClipVoteView(int(mid), len(info.get("voters", []))))
                    restored += 1
                except Exception as e:
                    logger.error(f"Failed to restore vote view for clip {mid}: {e}")
            logger.info(f"Clips persistent views restored (panel + {restored} vote views).")
        except Exception as e:
            logger.error(f"Failed to restore clip views on_ready: {e}")

    # --------------------------------------------------------------------------
    # STATELESS INTERACTION LISTENER
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""

        if custom_id == "clips_submit_panel":
            try:
                await interaction.response.send_message(
                    "🎬 **Submit a Clip** — pick a category, then paste a **Medal** or **YouTube** link or **upload from PC**.",
                    view=ClipCategoryView(self),
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Failed to open submit flow: {e}")
            return

        if custom_id.startswith("clip_fire_"):
            mid = custom_id.replace("clip_fire_", "")
            await self._handle_vote(interaction, mid)
            return

    # --------------------------------------------------------------------------
    # METADATA SCRAPER
    # --------------------------------------------------------------------------
    async def _fetch_youtube_metadata(self, url: str):
        title, thumbnail = None, None
        vid = _youtube_id(url)
        if vid:
            thumbnail = f"https://img.youtube.com/vi/{vid}/hqdefault.jpg"
        session = await self._get_session()
        try:
            oembed = f"https://www.youtube.com/oembed?url={quote(url, safe='')}&format=json"
            async with session.get(oembed, headers=UA_HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    title = data.get("title")
                    if not thumbnail and data.get("thumbnail_url"):
                        thumbnail = data.get("thumbnail_url")
        except Exception as e:
            logger.warning(f"YouTube oEmbed failed for {url}: {e}")
        if not title:
            title = "YouTube Clip"
        return title, thumbnail

    async def _fetch_medal_metadata(self, url: str):
        """Returns (title, thumbnail). Graceful fallback on every failure path."""
        title, thumbnail = None, None
        session = await self._get_session()

        try:
            async with session.get(url, headers=UA_HEADERS, allow_redirects=True, timeout=15) as resp:
                html = await resp.text()

            # Primary: locate the content hash embedded in the social video endpoint.
            m = re.search(r"/api/content/([\w-]+)/socialVideoUrl", html)
            if m:
                chash = m.group(1)
                try:
                    api_url = f"https://medal.tv/api/content/{chash}"
                    async with session.get(api_url, headers=UA_HEADERS, timeout=15) as r2:
                        if r2.status == 200:
                            data = await r2.json(content_type=None)
                            title = data.get("contentTitle") or data.get("title")
                            thumbnail = (
                                data.get("contentThumbnail")
                                or data.get("thumbnailUrl")
                                or data.get("contentThumbnail1080")
                            )
                except Exception as e:
                    logger.warning(f"Medal content API fetch failed ({chash}): {e}")

            # Fallback: Open Graph / Twitter card tags from the HTML.
            if not title:
                title = _extract_og(html, "og:title") or _extract_og(html, "twitter:title")
            if not thumbnail:
                thumbnail = _extract_og(html, "og:image") or _extract_og(html, "twitter:image")

        except Exception as e:
            logger.warning(f"Medal HTML scrape failed for {url}: {e}")

        # Last-resort: official developer search API (if a key is configured).
        if (not title or title == "Untitled Clip" or not thumbnail) and MEDAL_API_KEY:
            try:
                search_url = f"https://developers.medal.tv/v1/search?text={quote(url, safe='')}&limit=1"
                async with session.get(
                    search_url,
                    headers={**UA_HEADERS, "Authorization": MEDAL_API_KEY},
                    timeout=15,
                ) as r3:
                    if r3.status == 200:
                        payload = await r3.json(content_type=None)
                        items = payload.get("contentObjects") or payload.get("results") or []
                        if items:
                            item = items[0]
                            title = title or item.get("contentTitle") or item.get("title")
                            thumbnail = thumbnail or item.get("contentThumbnail") or item.get("thumbnailUrl")
            except Exception as e:
                logger.warning(f"Medal developer search fallback failed: {e}")

        # Sanitize the title — Medal often appends its own suffix or returns a generic landing title.
        if title:
            title = re.sub(r"\s*[-|]\s*(Clipped\s+.+?\s+with\s+)?Medal\.tv\s*$", "", title, flags=re.I).strip()
            title = re.sub(r"&amp;", "&", title)
            if any(marker in title.lower() for marker in GENERIC_MEDAL_TITLE_MARKERS):
                title = None
        if not title:
            title = "Untitled Clip"

        return title, thumbnail

    async def _fetch_clip_metadata(self, url: str):
        if _is_valid_youtube_url(url):
            return await self._fetch_youtube_metadata(url)
        return await self._fetch_medal_metadata(url)

    # --------------------------------------------------------------------------
    # EMBED BUILDER
    # --------------------------------------------------------------------------
    def _build_clip_embed(self, title, category, url, thumbnail, author, gold=False, source: str = "link"):
        emoji = CATEGORY_EMOJI.get(category, "🎬")
        embed = discord.Embed(
            title=f"{emoji} [{category}] {title}"[:256],
            url=url if url else None,
            color=THEME_GOLD if gold else THEME_PRIMARY,
        )
        if thumbnail:
            embed.set_image(url=thumbnail)
        if author:
            embed.set_author(
                name=author.display_name,
                icon_url=author.display_avatar.url if author.display_avatar else None,
            )
        footer = "🏛️ Hall of Fame" if gold else "ShadowSyn Clips • React with 🔥 to vote"
        if source == "upload":
            footer = f"{footer} • Uploaded clip"
        embed.set_footer(text=footer)
        return embed

    async def _finalize_clip_post(
        self,
        channel: discord.TextChannel,
        embed: discord.Embed,
        category: str,
        title: str,
        author: discord.User | discord.Member,
        *,
        url: str | None = None,
        thumbnail: str | None = None,
        source: str = "link",
        file: discord.File | None = None,
        reply_interaction: discord.Interaction | None = None,
        reply_dm: discord.DMChannel | None = None,
    ):
        try:
            if file:
                msg = await channel.send(embed=embed, file=file)
            else:
                msg = await channel.send(embed=embed)
        except Exception as e:
            logger.error(f"Failed to post clip embed: {e}")
            err = "❌ Failed to post your clip. Try again shortly."
            if reply_interaction:
                await safe_reply(reply_interaction, err, ephemeral=True)
            elif reply_dm:
                await reply_dm.send(err)
            return None

        vote_view = ClipVoteView(msg.id, 0)
        try:
            await msg.edit(view=vote_view)
            self.bot.add_view(vote_view)
        except Exception as e:
            logger.error(f"Failed to attach vote view to clip {msg.id}: {e}")

        try:
            await msg.create_thread(
                name=(title[:90] or "Clip Discussion"),
                auto_archive_duration=10080,
            )
        except Exception as e:
            logger.warning(f"Failed to create banter thread for clip {msg.id}: {e}")

        self.data["clips"][str(msg.id)] = {
            "voters": [],
            "hof_posted": False,
            "title": title,
            "category": category,
            "url": url,
            "author_id": author.id,
            "thumbnail": thumbnail,
            "source": source,
        }
        self._save()

        ok = f"✅ Clip posted to {channel.mention}!"
        if reply_interaction:
            await safe_reply(reply_interaction, ok, ephemeral=True)
        elif reply_dm:
            await reply_dm.send(ok)
        return msg

    # --------------------------------------------------------------------------
    # CLIP PUBLICATION
    # --------------------------------------------------------------------------
    async def publish_clip(self, interaction: discord.Interaction, url: str, category: str):
        channel = self.bot.get_channel(CLIPS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(CLIPS_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Clips channel unavailable: {e}")
                return await safe_reply(interaction, "❌ Clips channel is unavailable. Tell an admin.", ephemeral=True)

        title, thumbnail = await self._fetch_clip_metadata(url)
        source = "youtube" if _is_valid_youtube_url(url) else "medal"
        embed = self._build_clip_embed(title, category, url, thumbnail, interaction.user, source=source)
        await self._finalize_clip_post(
            channel,
            embed,
            category,
            title,
            interaction.user,
            url=url,
            thumbnail=thumbnail,
            source=source,
            reply_interaction=interaction,
        )

    async def publish_clip_file(
        self,
        author: discord.User | discord.Member,
        attachment: discord.Attachment,
        category: str,
        dm_channel: discord.DMChannel,
    ):
        channel = self.bot.get_channel(CLIPS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(CLIPS_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Clips channel unavailable: {e}")
                await dm_channel.send("❌ Clips channel is unavailable. Tell an admin.")
                return

        guild = channel.guild or await self._resolve_guild()
        max_bytes = self._upload_limit_bytes(guild)
        if attachment.size > max_bytes:
            await dm_channel.send(
                f"❌ File too large (**{_format_mb(attachment.size)}MB**). "
                f"This server allows up to **{_format_mb(max_bytes)}MB** per file "
                "(boost tier sets the cap — 25 / 50 / 100 MB)."
            )
            return

        content_type = (attachment.content_type or "").split(";")[0].strip().lower()
        if content_type and content_type not in UPLOAD_VIDEO_TYPES:
            await dm_channel.send(
                "❌ Unsupported file type. Send a video (`mp4`, `webm`, `mov`)."
            )
            return

        title = Path(attachment.filename or "Uploaded Clip").stem[:80] or "Uploaded Clip"
        embed = self._build_clip_embed(
            title, category, None, None, author, source="upload",
        )

        try:
            clip_file = await attachment.to_file()
        except Exception as e:
            logger.error(f"Failed to read attachment {attachment.id}: {e}")
            await dm_channel.send("❌ Could not read that file. Try again.")
            return

        await self._finalize_clip_post(
            channel,
            embed,
            category,
            title,
            author,
            source="upload",
            file=clip_file,
            reply_dm=dm_channel,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.DMChannel):
            return
        category = self._pending_uploads.pop(message.author.id, None)
        if not category:
            return
        if not message.attachments:
            await message.channel.send("📎 Attach a video file to this DM.")
            self._pending_uploads[message.author.id] = category
            return
        if len(message.attachments) > 1:
            await message.channel.send("❌ Send **one** video file per upload.")
            self._pending_uploads[message.author.id] = category
            return
        try:
            await self.publish_clip_file(
                message.author,
                message.attachments[0],
                category,
                message.channel,
            )
        except Exception as e:
            logger.error(f"DM clip upload failed for {message.author.id}: {e}")
            await message.channel.send("❌ Upload failed. Try again or use a link instead.")

    # --------------------------------------------------------------------------
    # VOTE HANDLING
    # --------------------------------------------------------------------------
    async def _handle_vote(self, interaction: discord.Interaction, mid: str):
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        clip = self.data["clips"].get(mid)
        if clip is None:
            # Self-heal for clips posted before this build / lost from persistence.
            clip = {"voters": [], "hof_posted": False, "title": None, "category": "Other",
                    "url": None, "author_id": None, "thumbnail": None}
            self.data["clips"][mid] = clip

        voters = clip.setdefault("voters", [])
        uid = interaction.user.id
        if uid in voters:
            voters.remove(uid)
            voted = False
        else:
            voters.append(uid)
            voted = True
        count = len(voters)
        self._save()

        inducting = count >= HOF_VOTE_THRESHOLD and not clip.get("hof_posted")
        gold_embed = None

        try:
            new_view = ClipVoteView(int(mid), count)
            if inducting and interaction.message and interaction.message.embeds:
                gold_embed = interaction.message.embeds[0].copy()
                gold_embed.color = discord.Color(THEME_GOLD)
                await interaction.message.edit(embed=gold_embed, view=new_view)
            else:
                await interaction.message.edit(view=new_view)
        except Exception as e:
            logger.error(f"Failed to update vote view for clip {mid}: {e}")

        if inducting:
            source_embed = gold_embed or (interaction.message.embeds[0] if (interaction.message and interaction.message.embeds) else None)
            posted = await self._induct_hof(interaction.guild, source_embed)
            if posted:
                clip["hof_posted"] = True
                self._save()
                await safe_reply(
                    interaction,
                    "🏆 This clip passed the vote threshold and was inducted into the Hall of Fame!",
                    ephemeral=True,
                )
                return

        await safe_reply(
            interaction,
            f"🔥 Vote {'added' if voted else 'removed'} — **{count}** total.",
            ephemeral=True,
        )

    # --------------------------------------------------------------------------
    # HALL OF FAME
    # --------------------------------------------------------------------------
    async def _resolve_hof_destination(self, guild: discord.Guild):
        target_id = CLIPS_HOF_CHANNEL_ID or self.data.get("hof_thread_id")
        if not target_id:
            return None
        dest = self.bot.get_channel(int(target_id))
        if dest is None:
            try:
                dest = await self.bot.fetch_channel(int(target_id))
            except Exception as e:
                logger.error(f"Hall of Fame destination {target_id} unavailable: {e}")
                return None
        return dest

    async def _induct_hof(self, guild: discord.Guild, source_embed: discord.Embed):
        if source_embed is None:
            return False
        dest = await self._resolve_hof_destination(guild)
        if dest is None:
            logger.warning("No Hall of Fame destination configured; skipping induction.")
            return False
        try:
            clone = source_embed.copy()
            clone.color = discord.Color(THEME_GOLD)
            clone.set_footer(text="🏛️ Inducted into the Hall of Fame")
            await dest.send(embed=clone)
            return True
        except Exception as e:
            logger.error(f"Failed to post clip to Hall of Fame: {e}")
            return False

    # --------------------------------------------------------------------------
    # GALLERY PERMISSION LOCK
    # --------------------------------------------------------------------------
    async def _lock_gallery_permissions(self, channel: discord.TextChannel):
        """
        Gallery channel is bot-post only. Deny top-level send for @everyone and
        every role/member with a channel overwrite. Banter stays in clip threads.
        """
        if not isinstance(channel, discord.TextChannel):
            return False, "Not a text channel."

        guild = channel.guild
        if guild is None:
            return False, "Channel has no guild context."

        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            return False, "Bot lacks **Manage Channels** to update permissions."

        reason = "ShadowSyn clips: gallery is ingest-only (use Submit Clip)"
        skip_ids: set[int] = {me.id}
        if me.top_role:
            skip_ids.add(me.top_role.id)

        targets: list[discord.Role | discord.Member] = [guild.default_role]
        for target in channel.overwrites:
            tid = target.id
            if tid in skip_ids:
                continue
            if target not in targets:
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
                ow.send_messages_in_threads = True
                await channel.set_permissions(target, overwrite=ow, reason=reason)
                updated += 1
            logger.info(f"Gallery permissions locked for {updated} target(s) in {channel.id}.")
            return True, f"Messaging locked for **{updated}** permission target(s)."
        except discord.Forbidden:
            logger.error("Forbidden while locking clips gallery permissions.")
            return False, "Forbidden — check bot **Manage Channels** and role hierarchy."
        except Exception as e:
            logger.error(f"Gallery permission lock failed: {e}")
            return False, str(e)

    # --------------------------------------------------------------------------
    # ADMIN DEPLOYMENT
    # --------------------------------------------------------------------------
    @discord.slash_command(
        name="clips_deploy",
        description="Deploy the clips ingest panel and build the Hall of Fame.",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions(administrator=True),
    )
    @commands.has_role(ROLE_ADMIN_ID)
    async def clips_deploy(self, ctx: discord.ApplicationContext):
        await safe_reply(ctx, "🛠️ Deploying clips system...", ephemeral=True)

        channel = self.bot.get_channel(CLIPS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(CLIPS_CHANNEL_ID)
            except Exception as e:
                return await safe_reply(ctx, f"❌ Clips channel unavailable: {e}", ephemeral=True)

        if not isinstance(channel, discord.TextChannel):
            return await safe_reply(ctx, "❌ Clips channel must be a text channel.", ephemeral=True)

        try:
            channel = await ctx.guild.fetch_channel(CLIPS_CHANNEL_ID)
        except Exception as e:
            logger.warning(f"Could not refresh clips channel before permission lock: {e}")

        perm_ok, perm_status = await self._lock_gallery_permissions(channel)
        if not perm_ok:
            return await safe_reply(
                ctx,
                f"❌ Could not lock gallery permissions: {perm_status}",
                ephemeral=True,
            )

        # --- Ingest panel ---
        panel_embed = discord.Embed(
            title="🎬 Clips",
            description=(
                "Drop your best clips here.\n\n"
                "Hit **Submit Clip**, pick a category, then paste a "
                "**Medal.tv** or **YouTube** link — or **upload from PC** "
                "(Shadow will DM you for the file). Each post gets its own "
                "thread for chat.\n\n"
                "React with 🔥 on clips you rate. Once a clip passes the vote "
                "threshold it gets moved to the **Hall of Fame**."
            ),
            color=THEME_PRIMARY,
        )
        panel_embed.set_footer(text="ShadowSyn Clips • React with 🔥 to vote")

        panel_msg = None
        existing_panel_id = self.data.get("panel_message_id")
        if existing_panel_id:
            try:
                panel_msg = await channel.fetch_message(int(existing_panel_id))
                await panel_msg.edit(embed=panel_embed, view=SubmitClipPanelView())
            except (discord.NotFound, discord.Forbidden, discord.HTTPException) as e:
                logger.warning(f"Existing clips panel {existing_panel_id} unavailable ({e}); redeploying fresh.")
                panel_msg = None

        if panel_msg is None:
            try:
                panel_msg = await channel.send(embed=panel_embed, view=SubmitClipPanelView())
                self.data["panel_message_id"] = panel_msg.id
            except Exception as e:
                logger.error(f"Failed to deploy ingest panel: {e}")
                return await safe_reply(ctx, f"❌ Failed to deploy ingest panel: {e}", ephemeral=True)

        try:
            await panel_msg.pin()
        except Exception as e:
            logger.warning(f"Failed to pin clips panel: {e}")

        # --- Hall of Fame: locked thread on the ingest panel (no extra gallery message) ---
        if CLIPS_HOF_CHANNEL_ID:
            hof_status = f"Using external Hall of Fame channel: <#{CLIPS_HOF_CHANNEL_ID}>"
        elif self.data.get("hof_thread_id"):
            hof_status = f"Reusing Hall of Fame thread: <#{self.data['hof_thread_id']}>"
        else:
            hof_status = "No Hall of Fame thread created."
            try:
                hof_thread = await panel_msg.create_thread(
                    name="🏛️ Hall of Fame",
                    auto_archive_duration=10080,
                )
                try:
                    await hof_thread.edit(locked=True)
                except Exception as e:
                    logger.warning(f"Failed to lock Hall of Fame thread: {e}")
                self.data["hof_thread_id"] = hof_thread.id
                hof_status = f"Hall of Fame thread created: <#{hof_thread.id}> (locked, read-only)"
            except Exception as e:
                logger.error(f"Failed to build Hall of Fame thread: {e}")
                hof_status = f"⚠️ HOF thread failed: {e}"

        self._save()

        await safe_reply(
            ctx,
            f"✅ Clips system deployed in {channel.mention}.\n"
            f"• {perm_status}\n"
            f"• Panel pinned (ID `{self.data['panel_message_id']}`)\n"
            f"• {hof_status}",
            ephemeral=True,
        )

    @clips_deploy.error
    async def clips_deploy_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, (commands.MissingRole, commands.CheckFailure)):
            await safe_reply(ctx, "🚫 Admin clearance required to deploy the clips system.", ephemeral=True)
        else:
            logger.error(f"clips_deploy error: {error}")
            await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)


# ==============================================================================
# ENTRY POINT
# ==============================================================================
def setup(bot: discord.Bot):
    bot.add_cog(ClipsCog(bot))
