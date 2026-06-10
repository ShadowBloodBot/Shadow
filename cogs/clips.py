# cogs/clips.py
import io
import os
import re
import json
import asyncio
import logging
from pathlib import Path
from urllib.parse import quote, urlparse, urlunparse

import aiohttp
import discord
from discord import Interaction, ButtonStyle
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
HOF_VOTE_THRESHOLD = 10
INGEST_PANEL_TITLE = "🎬 Clips"
INGEST_PANEL_DESCRIPTION = (
    "Hit **Submit Clip** — paste a Medal / YouTube link or upload a file.\n"
    "Each clip gets a thread. Enough 🔥 and it lands in the **Hall of Fame**."
)

try:
    CLIPS_HOF_CHANNEL_ID = int(os.getenv("CLIPS_HOF_CHANNEL_ID", "0")) or None
except (TypeError, ValueError):
    CLIPS_HOF_CHANNEL_ID = None

MEDAL_API_KEY = os.getenv("MEDAL_API_KEY")

UA_HEADERS = {"User-Agent": "ShadowSyn/1.0 (+https://medal.tv)"}

MEDAL_HOST_RE = re.compile(r"^https?://(?:www\.)?medal\.tv/", re.I)
MEDAL_CLIP_PATH_RE = re.compile(
    r"(?:"
    r"clip/[\w-]+"
    r"|clips/[\w-]+"
    r"|games/[\w-]+/clips?/[\w-]+"
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

CLIPS_STORE = PERSIST_ROOT / "clips_repo.json"


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
        if hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception:
        return None


def _medal_path(url: str) -> str:
    return url.split("medal.tv/", 1)[-1].split("?")[0].strip("/")


def _medal_content_id(url: str) -> str | None:
    """Extract Medal content hash from any supported clip URL shape."""
    path = _medal_path(_normalize_clip_url(url))
    if not path:
        return None
    for pat in (
        r"games/[\w-]+/clips?/([\w-]+)$",
        r"clips?/([\w-]+)$",
    ):
        m = re.search(pat, path, re.I)
        if m:
            return m.group(1)
    return None


MEDAL_VIDEO_KEYS = (
    "contentUrl720p",
    "contentUrl480p",
    "contentUrl360p",
    "contentUrl240p",
    "contentUrl1080p",
    "contentUrl",
    "socialMediaVideo",
)


def _parse_medal_api_payload(data: dict) -> tuple[str | None, str | None, list[str]]:
    """Returns (title, thumbnail, video_url_candidates) from Medal /api/content JSON."""
    title = data.get("contentTitle") or data.get("title")
    thumbnail = (
        data.get("thumbnailUrl")
        or data.get("thumbnail720p")
        or data.get("thumbnail1080p")
        or data.get("contentThumbnail")
        or data.get("contentThumbnail1080")
    )
    seen: set[str] = set()
    video_urls: list[str] = []
    for key in MEDAL_VIDEO_KEYS:
        url = data.get(key)
        if url and url not in seen:
            seen.add(url)
            video_urls.append(url)
    return title, thumbnail, video_urls


def _normalize_clip_url(url: str) -> str:
    """Trim whitespace; drop Medal tracking params so links validate and store cleanly."""
    url = url.strip()
    if not MEDAL_HOST_RE.match(url):
        return url
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def _is_valid_medal_url(url: str) -> bool:
    if not url:
        return False
    url = _normalize_clip_url(url)
    if not MEDAL_HOST_RE.match(url):
        return False
    path = _medal_path(url)
    return bool(path and MEDAL_CLIP_PATH_RE.search(path))


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


def _thread_name(author: discord.User | discord.Member, title: str | None) -> str:
    """Thread label: poster first, title as fallback."""
    name = (getattr(author, "display_name", None) or str(author))[:90]
    if name:
        return name
    return (title[:90] if title else "Clip") or "Clip"


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
    """Persistent ingest panel — handled in on_interaction."""

    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(
            label="Submit Clip",
            style=ButtonStyle.primary,
            emoji="🎬",
            custom_id="clips_submit_panel",
        ))


class ClipLinkButton(Button):
    def __init__(self, cog, user_id: int):
        super().__init__(label="Paste Link", style=ButtonStyle.primary, emoji="🔗")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        self.cog._flow_track(self.user_id, interaction)
        await interaction.response.send_modal(ClipUrlModal(self.cog, self.user_id))


class ClipUploadButton(Button):
    def __init__(self, cog, user_id: int):
        super().__init__(label="Upload from PC", style=ButtonStyle.secondary, emoji="📁")
        self.cog = cog
        self.user_id = user_id

    async def callback(self, interaction: Interaction):
        self.cog._flow_track(self.user_id, interaction)
        self.cog._flow_set_upload_pending(self.user_id)
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild or await self.cog._resolve_guild()
        max_bytes = self.cog._upload_limit_bytes(guild)
        try:
            dm = await interaction.user.create_dm()
            prompt = await dm.send(
                f"Drop your clip here — `mp4`, `webm`, or `mov` (max **{_format_mb(max_bytes)}MB**)."
            )
            self.cog._flow_set_dm_prompt(self.user_id, prompt.id)
        except discord.Forbidden:
            self.cog._flow_clear(self.user_id)
            await interaction.followup.send(
                "❌ Enable DMs from server members to upload files.",
                ephemeral=True,
            )
        except Exception as e:
            self.cog._flow_clear(self.user_id)
            logger.error(f"Failed to open upload DM for {self.user_id}: {e}")
            await interaction.followup.send("❌ Could not open upload DM. Try again.", ephemeral=True)


class ClipSourceView(View):
    """Ephemeral: link or file — one step after Submit Clip."""

    def __init__(self, cog, user_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.user_id = user_id
        self.add_item(ClipLinkButton(cog, user_id))
        self.add_item(ClipUploadButton(cog, user_id))

    async def on_timeout(self):
        self.cog._flow_clear(self.user_id)


class ClipUrlModal(Modal):
    def __init__(self, cog, user_id: int):
        super().__init__(title="Clip Link")
        self.cog = cog
        self.user_id = user_id
        self.add_item(TextInput(
            label="Medal or YouTube URL",
            placeholder="https://medal.tv/... or https://youtu.be/...",
            style=discord.InputTextStyle.short,
            required=True,
            max_length=400,
        ))

    async def callback(self, interaction: Interaction):
        raw = self.children[0].value.strip()
        url = _normalize_clip_url(raw)
        if not _is_valid_clip_url(url):
            return await safe_reply(
                interaction,
                "❌ That doesn't look like a Medal or YouTube clip link.",
                ephemeral=True,
            )
        self.cog._flow_track(self.user_id, interaction)
        await interaction.response.defer(ephemeral=True)
        await self.cog.publish_clip(interaction, url)


class ClipVoteView(View):
    def __init__(self, message_id: int, count: int = 0):
        super().__init__(timeout=None)
        self.add_item(Button(
            label=str(count) if count else "\u200b",
            emoji="🔥",
            style=ButtonStyle.secondary,
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
        self._flow_sessions: dict[int, dict] = {}
        self._load_data()

    def cog_unload(self):
        if self.session and not self.session.closed:
            asyncio.create_task(self.session.close())
        logger.info("ClipsCog unloaded. aiohttp session scheduled for closure.")

    # --------------------------------------------------------------------------
    # PERSISTENCE
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

    async def _clips_channel(self) -> discord.TextChannel | None:
        channel = self.bot.get_channel(CLIPS_CHANNEL_ID)
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(CLIPS_CHANNEL_ID)
            except Exception as e:
                logger.error(f"Clips channel unavailable: {e}")
                return None
        return channel if isinstance(channel, discord.TextChannel) else None

    def _upload_limit_bytes(self, guild: discord.Guild | None) -> int:
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
    # SUBMIT FLOW (ephemeral cleanup)
    # --------------------------------------------------------------------------
    def _flow_begin(self, user_id: int, interaction: discord.Interaction):
        self._flow_sessions[user_id] = {
            "upload_pending": False,
            "interactions": [interaction],
            "dm_prompt_id": None,
        }

    def _flow_track(self, user_id: int, interaction: discord.Interaction):
        sess = self._flow_sessions.get(user_id)
        if sess is not None:
            sess["interactions"].append(interaction)

    def _flow_set_upload_pending(self, user_id: int):
        sess = self._flow_sessions.get(user_id)
        if sess is not None:
            sess["upload_pending"] = True

    def _flow_set_dm_prompt(self, user_id: int, message_id: int):
        sess = self._flow_sessions.get(user_id)
        if sess is not None:
            sess["dm_prompt_id"] = message_id

    def _flow_clear(self, user_id: int):
        self._flow_sessions.pop(user_id, None)

    async def _flow_cleanup(
        self,
        user_id: int,
        *,
        dm_channel: discord.DMChannel | None = None,
        user_message: discord.Message | None = None,
    ):
        sess = self._flow_sessions.pop(user_id, None)
        if not sess:
            return
        for inter in sess.get("interactions", []):
            try:
                await inter.delete_original_response()
            except Exception:
                pass
        if dm_channel and sess.get("dm_prompt_id"):
            try:
                prompt = await dm_channel.fetch_message(sess["dm_prompt_id"])
                await prompt.delete()
            except Exception:
                pass
        if user_message:
            try:
                await user_message.delete()
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # PERSISTENT VIEWS
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

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "") if interaction.data else ""

        if custom_id == "clips_submit_panel":
            try:
                self._flow_begin(interaction.user.id, interaction)
                await interaction.response.send_message(
                    view=ClipSourceView(self, interaction.user.id),
                    ephemeral=True,
                )
            except Exception as e:
                logger.error(f"Failed to open submit flow: {e}")
            return

        if custom_id.startswith("clip_fire_"):
            mid = custom_id.replace("clip_fire_", "")
            await self._handle_vote(interaction, mid)

    # --------------------------------------------------------------------------
    # METADATA
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
        return title or "YouTube Clip", thumbnail

    async def _fetch_medal_api(self, content_id: str) -> dict | None:
        session = await self._get_session()
        try:
            api_url = f"https://medal.tv/api/content/{content_id}"
            async with session.get(api_url, headers=UA_HEADERS, timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"Medal API fetch failed ({content_id}): {e}")
        return None

    async def _fetch_medal_metadata(self, url: str) -> tuple[str, str | None, list[str]]:
        """Returns (title, thumbnail, video_url_candidates). API-first using the clip id in the URL."""
        title, thumbnail, video_urls = None, None, []
        session = await self._get_session()
        clean = _normalize_clip_url(url)
        api_data: dict | None = None

        content_id = _medal_content_id(clean)
        if content_id:
            api_data = await self._fetch_medal_api(content_id)
            if api_data:
                title, thumbnail, video_urls = _parse_medal_api_payload(api_data)

        if not title or not video_urls:
            try:
                async with session.get(clean, headers=UA_HEADERS, allow_redirects=True, timeout=15) as resp:
                    html = await resp.text()
                if not api_data:
                    m = re.search(r"/api/content/([\w-]+)/socialVideoUrl", html)
                    if m:
                        api_data = await self._fetch_medal_api(m.group(1))
                        if api_data:
                            t, th, vids = _parse_medal_api_payload(api_data)
                            title = title or t
                            thumbnail = thumbnail or th
                            video_urls = video_urls or vids
                if not title:
                    title = _extract_og(html, "og:title") or _extract_og(html, "twitter:title")
                if not thumbnail:
                    thumbnail = _extract_og(html, "og:image") or _extract_og(html, "twitter:image")
            except Exception as e:
                logger.warning(f"Medal HTML scrape failed for {clean}: {e}")

        if (not title or not video_urls) and MEDAL_API_KEY:
            try:
                search_url = f"https://developers.medal.tv/v1/search?text={quote(clean, safe='')}&limit=1"
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
                            thumbnail = thumbnail or item.get("thumbnailUrl") or item.get("contentThumbnail")
                            for key in MEDAL_VIDEO_KEYS:
                                u = item.get(key)
                                if u and u not in video_urls:
                                    video_urls.append(u)
            except Exception as e:
                logger.warning(f"Medal developer search fallback failed: {e}")

        if title:
            title = re.sub(r"\s*[-|]\s*(Clipped\s+.+?\s+with\s+)?Medal\.tv\s*$", "", title, flags=re.I).strip()
            title = re.sub(r"&amp;", "&", title)
            if any(marker in title.lower() for marker in GENERIC_MEDAL_TITLE_MARKERS):
                title = None

        return title or "Untitled Clip", thumbnail, video_urls

    async def _probe_video_size(self, video_url: str) -> int | None:
        session = await self._get_session()
        try:
            async with session.head(video_url, headers=UA_HEADERS, allow_redirects=True, timeout=20) as resp:
                if resp.status != 200:
                    return None
                cl = resp.headers.get("Content-Length")
                return int(cl) if cl else None
        except Exception:
            return None

    async def _download_medal_video(self, video_url: str, max_bytes: int) -> discord.File | None:
        """Stream Medal MP4 into a Discord attachment — native inline playback."""
        session = await self._get_session()
        try:
            async with session.get(video_url, headers=UA_HEADERS, allow_redirects=True, timeout=180) as resp:
                if resp.status != 200:
                    logger.warning(f"Medal video download status {resp.status} for {video_url[:80]}")
                    return None
                cl = resp.headers.get("Content-Length")
                if cl and int(cl) > max_bytes:
                    return None
                buf = bytearray()
                async for chunk in resp.content.iter_chunked(512 * 1024):
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        return None
                if not buf:
                    return None
                logger.info(f"Medal video ready ({len(buf) / (1024 * 1024):.1f}MB).")
                payload = io.BytesIO(bytes(buf))
                payload.seek(0)
                return discord.File(payload, filename="clip.mp4", spoiler=False)
        except Exception as e:
            logger.warning(f"Medal video download failed: {e}")
            return None

    async def _download_best_medal_video(self, candidates: list[str], max_bytes: int) -> discord.File | None:
        """
        Pick the highest-quality Medal URL that fits the server cap.
        Probes sizes when available; falls back through the quality ladder.
        """
        if not candidates:
            return None

        sized: list[tuple[int, str]] = []
        unknown: list[str] = []
        for url in candidates:
            size = await self._probe_video_size(url)
            if size is None:
                unknown.append(url)
            elif size <= max_bytes:
                sized.append((size, url))

        ordered = [url for _, url in sorted(sized, key=lambda x: x[0], reverse=True)]
        ordered.extend(unknown)

        seen: set[str] = set()
        for url in ordered:
            if url in seen:
                continue
            seen.add(url)
            clip = await self._download_medal_video(url, max_bytes)
            if clip is not None:
                return clip
        return None

    # --------------------------------------------------------------------------
    # GALLERY POST
    # --------------------------------------------------------------------------
    def _build_clip_embed(
        self,
        author: discord.User | discord.Member,
        *,
        url: str | None = None,
        thumbnail: str | None = None,
        gold: bool = False,
        video_attached: bool = False,
    ) -> discord.Embed:
        """
        video_attached: author bar only — Discord renders the MP4 player natively below.
        No external link or static thumbnail that looks like a broken player.
        """
        embed = discord.Embed(color=THEME_GOLD if gold else THEME_PRIMARY)
        if not video_attached:
            if url:
                embed.url = url
            if thumbnail:
                embed.set_image(url=thumbnail)
        embed.set_author(
            name=author.display_name,
            icon_url=author.display_avatar.url if author.display_avatar else None,
        )
        if gold:
            embed.set_footer(text="🏛️ Hall of Fame")
        return embed

    async def _finalize_clip_post(
        self,
        channel: discord.TextChannel,
        embed: discord.Embed,
        title: str,
        author: discord.User | discord.Member,
        *,
        url: str | None = None,
        thumbnail: str | None = None,
        source: str = "link",
        file: discord.File | None = None,
        reply_interaction: discord.Interaction | None = None,
        reply_dm: discord.DMChannel | None = None,
        cleanup_user_message: discord.Message | None = None,
    ):
        try:
            msg = await channel.send(embed=embed, file=file) if file else await channel.send(embed=embed)
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
                name=_thread_name(author, title),
                auto_archive_duration=10080,
            )
        except Exception as e:
            logger.warning(f"Failed to create banter thread for clip {msg.id}: {e}")

        self.data["clips"][str(msg.id)] = {
            "voters": [],
            "hof_posted": False,
            "title": title,
            "url": url,
            "author_id": author.id,
            "thumbnail": thumbnail,
            "source": source,
        }
        self._save()

        try:
            await self._refresh_ingest_panel(channel)
        except Exception as e:
            logger.warning(f"Ingest panel refresh after clip post failed: {e}")

        await self._flow_cleanup(
            author.id,
            dm_channel=reply_dm,
            user_message=cleanup_user_message,
        )
        return msg

    async def publish_clip(self, interaction: discord.Interaction, url: str):
        channel = await self._clips_channel()
        if channel is None:
            return await safe_reply(
                interaction,
                "❌ Clips channel is unavailable. Tell an admin.",
                ephemeral=True,
            )

        guild = channel.guild or await self._resolve_guild()
        # Leave 1 MB headroom for Discord attachment overhead.
        max_bytes = max(self._upload_limit_bytes(guild) - (1024 * 1024), 8 * 1024 * 1024)
        clip_file = None
        video_attached = False

        if _is_valid_youtube_url(url):
            title, thumbnail = await self._fetch_youtube_metadata(url)
            source = "youtube"
        else:
            title, thumbnail, video_urls = await self._fetch_medal_metadata(url)
            source = "medal"
            clip_file = await self._download_best_medal_video(video_urls, max_bytes)
            if clip_file is None:
                return await safe_reply(
                    interaction,
                    f"❌ Couldn't pull this Medal clip into Discord "
                    f"(server cap **{_format_mb(max_bytes)}MB**). "
                    "Try **Upload from PC** or a shorter clip.",
                    ephemeral=True,
                )
            video_attached = True

        embed = self._build_clip_embed(
            interaction.user,
            url=url,
            thumbnail=thumbnail,
            video_attached=video_attached,
        )
        await self._finalize_clip_post(
            channel,
            embed,
            title,
            interaction.user,
            url=url,
            thumbnail=thumbnail,
            source=source,
            file=clip_file,
            reply_interaction=interaction,
        )

    async def publish_clip_file(
        self,
        author: discord.User | discord.Member,
        attachment: discord.Attachment,
        dm_channel: discord.DMChannel,
        *,
        user_message: discord.Message | None = None,
    ):
        channel = await self._clips_channel()
        if channel is None:
            await dm_channel.send("❌ Clips channel is unavailable. Tell an admin.")
            return

        guild = channel.guild or await self._resolve_guild()
        max_bytes = self._upload_limit_bytes(guild)
        if attachment.size > max_bytes:
            await dm_channel.send(
                f"❌ Too large (**{_format_mb(attachment.size)}MB**). "
                f"Server cap is **{_format_mb(max_bytes)}MB**."
            )
            return

        content_type = (attachment.content_type or "").split(";")[0].strip().lower()
        if content_type and content_type not in UPLOAD_VIDEO_TYPES:
            await dm_channel.send("❌ Send a video file (`mp4`, `webm`, `mov`).")
            return

        title = Path(attachment.filename or "clip").stem[:80] or "Uploaded Clip"
        embed = self._build_clip_embed(author, video_attached=True)

        try:
            clip_file = await attachment.to_file()
        except Exception as e:
            logger.error(f"Failed to read attachment {attachment.id}: {e}")
            await dm_channel.send("❌ Could not read that file. Try again.")
            return

        await self._finalize_clip_post(
            channel,
            embed,
            title,
            author,
            source="upload",
            file=clip_file,
            reply_dm=dm_channel,
            cleanup_user_message=user_message,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.DMChannel):
            return
        sess = self._flow_sessions.get(message.author.id)
        if not sess or not sess.get("upload_pending"):
            return
        if not message.attachments:
            await message.channel.send("📎 Attach a video file.", delete_after=8)
            return
        if len(message.attachments) > 1:
            await message.channel.send("❌ One file only.", delete_after=8)
            return
        try:
            await self.publish_clip_file(
                message.author,
                message.attachments[0],
                message.channel,
                user_message=message,
            )
        except Exception as e:
            logger.error(f"DM clip upload failed for {message.author.id}: {e}")
            await message.channel.send("❌ Upload failed.", delete_after=8)

    # --------------------------------------------------------------------------
    # VOTING & HALL OF FAME
    # --------------------------------------------------------------------------
    async def _handle_vote(self, interaction: discord.Interaction, mid: str):
        try:
            await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        clip = self.data["clips"].get(mid)
        if clip is None:
            clip = {
                "voters": [],
                "hof_posted": False,
                "title": None,
                "url": None,
                "author_id": None,
                "thumbnail": None,
            }
            self.data["clips"][mid] = clip

        voters = clip.setdefault("voters", [])
        uid = interaction.user.id
        if uid in voters:
            voters.remove(uid)
        else:
            voters.append(uid)
        count = len(voters)
        self._save()

        inducting = count >= HOF_VOTE_THRESHOLD and not clip.get("hof_posted")
        gold_embed = None

        try:
            new_view = ClipVoteView(int(mid), count)
            if inducting and interaction.message and interaction.message.embeds:
                gold_embed = interaction.message.embeds[0].copy()
                gold_embed.color = discord.Color(THEME_GOLD)
                gold_embed.set_footer(text="🏛️ Hall of Fame")
                await interaction.message.edit(embed=gold_embed, view=new_view)
            else:
                await interaction.message.edit(view=new_view)
        except Exception as e:
            logger.error(f"Failed to update vote view for clip {mid}: {e}")

        if inducting:
            source_embed = gold_embed or (
                interaction.message.embeds[0]
                if interaction.message and interaction.message.embeds
                else None
            )
            if await self._induct_hof(interaction.guild, source_embed):
                clip["hof_posted"] = True
                self._save()
                try:
                    await interaction.followup.send(
                        "🏆 Hall of Fame!",
                        ephemeral=True,
                        delete_after=4,
                    )
                except Exception:
                    pass
                return

        try:
            await interaction.followup.send(f"🔥 {count}", ephemeral=True, delete_after=2)
        except Exception:
            pass

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
            clone.set_footer(text="🏛️ Hall of Fame")
            await dest.send(embed=clone)
            return True
        except Exception as e:
            logger.error(f"Failed to post clip to Hall of Fame: {e}")
            return False

    # --------------------------------------------------------------------------
    # INGEST PANEL
    # --------------------------------------------------------------------------
    def _build_ingest_panel_embed(self) -> discord.Embed:
        return discord.Embed(
            title=INGEST_PANEL_TITLE,
            description=INGEST_PANEL_DESCRIPTION,
            color=THEME_PRIMARY,
        )

    async def _delete_ingest_panel(self, channel: discord.TextChannel, message_id: int | str | None):
        if not message_id:
            return
        try:
            old_msg = await channel.fetch_message(int(message_id))
            try:
                await old_msg.unpin()
            except Exception:
                pass
            await old_msg.delete()
        except discord.NotFound:
            pass
        except Exception as e:
            logger.warning(f"Could not delete ingest panel {message_id}: {e}")

    async def _refresh_ingest_panel(self, channel: discord.TextChannel):
        await self._delete_ingest_panel(channel, self.data.get("panel_message_id"))

        view = SubmitClipPanelView()
        try:
            panel_msg = await channel.send(embed=self._build_ingest_panel_embed(), view=view)
            self.bot.add_view(view)
            self.data["panel_message_id"] = panel_msg.id
            self._save()
            logger.info(f"Ingest panel refreshed ({panel_msg.id}).")
        except Exception as e:
            logger.error(f"Failed to refresh ingest panel: {e}")

    # --------------------------------------------------------------------------
    # GALLERY PERMISSION LOCK
    # --------------------------------------------------------------------------
    async def _lock_gallery_permissions(self, channel: discord.TextChannel):
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
    # ADMIN DEPLOY
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

        channel = await self._clips_channel()
        if channel is None:
            return await safe_reply(ctx, "❌ Clips channel unavailable.", ephemeral=True)

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

        try:
            await self._refresh_ingest_panel(channel)
            panel_msg = await channel.fetch_message(int(self.data["panel_message_id"]))
        except Exception as e:
            logger.error(f"Failed to deploy ingest panel: {e}")
            return await safe_reply(ctx, f"❌ Failed to deploy ingest panel: {e}", ephemeral=True)

        if CLIPS_HOF_CHANNEL_ID:
            hof_status = f"Hall of Fame channel: <#{CLIPS_HOF_CHANNEL_ID}>"
        elif self.data.get("hof_thread_id"):
            hof_status = f"Hall of Fame thread: <#{self.data['hof_thread_id']}>"
        else:
            hof_status = "No Hall of Fame thread yet."
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
                hof_status = f"Hall of Fame thread: <#{hof_thread.id}> (locked)"
            except Exception as e:
                logger.error(f"Failed to build Hall of Fame thread: {e}")
                hof_status = f"⚠️ HOF thread failed: {e}"

        self._save()

        await safe_reply(
            ctx,
            f"✅ Clips live in {channel.mention}.\n"
            f"• {perm_status}\n"
            f"• Panel ID `{self.data['panel_message_id']}`\n"
            f"• {hof_status}",
            ephemeral=True,
        )

    @clips_deploy.error
    async def clips_deploy_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, (commands.MissingRole, commands.CheckFailure)):
            await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)
        else:
            logger.error(f"clips_deploy error: {error}")
            await safe_reply(ctx, f"⚠️ Error: {error}", ephemeral=True)


def setup(bot: discord.Bot):
    bot.add_cog(ClipsCog(bot))
