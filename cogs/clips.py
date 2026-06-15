# cogs/clips.py
import io
import os
import re
import json
import asyncio
import logging
import subprocess
import tempfile
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

from cogs.guild_registry import (
    REGISTERED_GUILD_IDS,
    SHADOW_MAIN_GUILD_ID,
    ch_id,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
    resolve_role,
    role_id,
)

# ==============================================================================
# CONSTANTS & IDS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627
INGEST_PANEL_TITLE = "🎬 Clips"
INGEST_PANEL_DESCRIPTION = (
    "Hit **Submit Clip** — paste a Medal / YouTube link or upload a file.\n"
    "Each clip gets a thread. Drop a 🔥 on the ones that deserve it."
)
HOF_THREAD_NAME = "🏛️ Hall of Fame"

MEDAL_API_KEY = os.getenv("MEDAL_API_KEY")

UA_HEADERS = {"User-Agent": "ShadowSyn/1.0 (+https://medal.tv)"}
METADATA_TIMEOUT = aiohttp.ClientTimeout(total=8)

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
# PC upload transcode ceiling — ffmpeg fit won't process absurd sources.
FFMPEG_SOURCE_MAX_BYTES = 512 * 1024 * 1024
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
    "contentUrl240p",
    "contentUrl360p",
    "contentUrl480p",
    "contentUrl720p",
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


def _ffmpeg_fit_to_cap_sync(src: bytes, max_bytes: int) -> bytes | None:
    """Re-encode to the largest quality that fits max_bytes — full duration, no trim."""
    if len(src) <= max_bytes:
        return src
    if len(src) > FFMPEG_SOURCE_MAX_BYTES:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        inp = Path(tmp) / "in.mp4"
        out = Path(tmp) / "out.mp4"
        inp.write_bytes(src)

        attempts: list[list[str]] = [
            [
                "ffmpeg", "-y", "-i", str(inp),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-movflags", "+faststart",
                "-fs", str(max_bytes),
                str(out),
            ],
            [
                "ffmpeg", "-y", "-i", str(inp),
                "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                "-vf", "scale='min(1280,iw)':-2",
                "-c:a", "aac", "-b:a", "96k",
                "-movflags", "+faststart",
                "-fs", str(max_bytes),
                str(out),
            ],
            [
                "ffmpeg", "-y", "-i", str(inp),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "32",
                "-vf", "scale='min(854,iw)':-2",
                "-c:a", "aac", "-b:a", "64k",
                "-movflags", "+faststart",
                "-fs", str(max_bytes),
                str(out),
            ],
        ]

        for cmd in attempts:
            out.unlink(missing_ok=True)
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=300,
                    check=False,
                )
            except subprocess.TimeoutExpired:
                logger.warning("ffmpeg transcode timed out")
                return None
            if result.returncode != 0:
                logger.warning(f"ffmpeg pass failed: {result.stderr[-400:].decode(errors='replace')}")
                continue
            if out.exists():
                size = out.stat().st_size
                if 0 < size <= max_bytes:
                    logger.info(f"ffmpeg fit OK ({size / (1024 * 1024):.1f}MB / cap {_format_mb(max_bytes)}MB).")
                    return out.read_bytes()
    return None


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

        # Primary path: private upload thread in the gallery — no DMs required.
        thread = await self.cog._open_upload_thread(interaction.user, max_bytes)
        if thread is not None:
            self.cog._flow_set_upload_thread(self.user_id, thread.id)
            await interaction.followup.send(
                f"📤 Drop your file in {thread.mention}.",
                ephemeral=True,
            )
            return

        # Fallback: DM upload (thread creation unavailable).
        try:
            dm = await interaction.user.create_dm()
            prompt = await dm.send(
                f"Drop your clip here — `mp4`, `webm`, or `mov` (max **{_format_mb(max_bytes)}MB**)."
            )
            self.cog._flow_set_dm_prompt(self.user_id, prompt.id)
            await interaction.followup.send("📬 Check your DMs to upload.", ephemeral=True)
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
        super().__init__(timeout=600)
        self.cog = cog
        self.user_id = user_id
        self.add_item(ClipLinkButton(cog, user_id))
        self.add_item(ClipUploadButton(cog, user_id))

    async def on_timeout(self):
        await self.cog._flow_cleanup(self.user_id)


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


# ==============================================================================
# CORE COG
# ==============================================================================
class ClipsCog(commands.Cog):
    def __init__(self, bot: discord.Bot):
        self.bot = bot
        self.session = None
        self.data = {"panels": {}, "clips": {}}
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
                panels = loaded.get("panels") or {}
                if not panels and loaded.get("panel_message_id"):
                    panels = {str(SHADOW_MAIN_GUILD_ID): loaded["panel_message_id"]}
                self.data["panels"] = panels
                self.data["clips"] = loaded.get("clips", {}) or {}
                logger.info(f"Loaded {len(self.data['clips'])} tracked clips from repo.")
            except Exception as e:
                logger.error(f"Corruption in {CLIPS_STORE.name}, starting fresh. Error: {e}")
                self.data = {"panels": {}, "clips": {}}
        else:
            logger.info("No existing clips repo found. Initializing empty state.")

    def _panel_id(self, guild_id: int) -> int | None:
        raw = self.data.get("panels", {}).get(str(guild_id))
        try:
            return int(raw) if raw else None
        except (TypeError, ValueError):
            return None

    def _set_panel_id(self, guild_id: int, message_id: int) -> None:
        self.data.setdefault("panels", {})[str(guild_id)] = message_id

    def _save(self):
        _atomic_write(CLIPS_STORE, self.data)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    async def _clips_channel(self, guild_id: int | None = None) -> discord.TextChannel | None:
        if guild_id is None:
            guild_id = SHADOW_MAIN_GUILD_ID
        channel = await resolve_channel(self.bot, guild_id, "clips")
        return channel if isinstance(channel, discord.TextChannel) else None

    def _upload_limit_bytes(self, guild: discord.Guild | None) -> int:
        if guild is not None and getattr(guild, "filesize_limit", None):
            return guild.filesize_limit
        return UPLOAD_FALLBACK_BYTES

    async def _ffmpeg_fit_to_cap(self, src: bytes, max_bytes: int) -> bytes | None:
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(None, _ffmpeg_fit_to_cap_sync, src, max_bytes)
        except Exception as e:
            logger.error(f"ffmpeg fit executor failed: {e}")
            return None

    async def _resolve_guild(self, guild_id: int | None = None) -> discord.Guild | None:
        gid = guild_id or SHADOW_MAIN_GUILD_ID
        guild = self.bot.get_guild(gid)
        if guild is None:
            try:
                guild = await self.bot.fetch_guild(gid)
            except Exception as e:
                logger.warning(f"Could not fetch guild {gid} for upload limit: {e}")
        return guild

    async def _open_upload_thread(
        self,
        user: discord.User | discord.Member,
        max_bytes: int,
    ) -> discord.Thread | None:
        """Private upload thread in the gallery — members can post there because
        the gallery lock allows send_messages_in_threads."""
        gid = user.guild.id if isinstance(user, discord.Member) and user.guild else SHADOW_MAIN_GUILD_ID
        channel = await self._clips_channel(guild_id=gid)
        if channel is None:
            return None
        try:
            name = f"📤 {getattr(user, 'display_name', None) or user}"[:95]
            thread = await channel.create_thread(
                name=name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=60,
                invitable=False,
            )
            await thread.add_user(user)
            await thread.send(
                f"{user.mention} drop your clip here — `mp4`, `webm`, or `mov` "
                f"(max **{_format_mb(max_bytes)}MB**)."
            )
            return thread
        except Exception as e:
            logger.warning(f"Could not open upload thread for {user.id}: {e}")
            return None

    # --------------------------------------------------------------------------
    # SUBMIT FLOW (ephemeral cleanup)
    # --------------------------------------------------------------------------
    def _flow_begin(self, user_id: int, interaction: discord.Interaction):
        self._flow_sessions[user_id] = {
            "upload_pending": False,
            "interactions": [interaction],
            "dm_prompt_id": None,
            "upload_thread_id": None,
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

    def _flow_set_upload_thread(self, user_id: int, thread_id: int):
        sess = self._flow_sessions.get(user_id)
        if sess is not None:
            sess["upload_thread_id"] = thread_id

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
        thread_id = sess.get("upload_thread_id")
        if thread_id:
            try:
                thread = self.bot.get_channel(thread_id) or await self.bot.fetch_channel(thread_id)
                await thread.delete()
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # PERSISTENT VIEWS
    # --------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_ready(self):
        try:
            self.bot.add_view(SubmitClipPanelView())
            logger.info("Clips persistent views restored (submit panel).")
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
            async with session.get(oembed, headers=UA_HEADERS, timeout=METADATA_TIMEOUT) as resp:
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
            async with session.get(api_url, headers=UA_HEADERS, timeout=METADATA_TIMEOUT) as resp:
                if resp.status == 200:
                    return await resp.json(content_type=None)
        except Exception as e:
            logger.warning(f"Medal API fetch failed ({content_id}): {e}")
        return None

    def _clean_medal_title(self, title: str | None) -> str | None:
        if not title:
            return None
        cleaned = re.sub(
            r"\s*[-|]\s*(Clipped\s+.+?\s+with\s+)?Medal\.tv\s*$", "", title, flags=re.I
        ).strip()
        cleaned = re.sub(r"&amp;", "&", cleaned)
        if any(marker in cleaned.lower() for marker in GENERIC_MEDAL_TITLE_MARKERS):
            return None
        return cleaned or None

    async def _fetch_medal_link_metadata(self, url: str) -> tuple[str, str | None]:
        """Fast Medal lookup for link posts — API only, no HTML scrape."""
        content_id = _medal_content_id(_normalize_clip_url(url))
        if not content_id:
            return "Medal Clip", None
        api_data = await self._fetch_medal_api(content_id)
        if not api_data:
            return "Medal Clip", None
        title, thumbnail, _ = _parse_medal_api_payload(api_data)
        return self._clean_medal_title(title) or "Medal Clip", thumbnail

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
            title = self._clean_medal_title(title)

        return title or "Untitled Clip", thumbnail, video_urls

    async def _create_banter_thread(
        self,
        msg: discord.Message,
        author: discord.User | discord.Member,
        title: str,
    ) -> None:
        try:
            await msg.create_thread(
                name=_thread_name(author, title),
                auto_archive_duration=10080,
            )
        except Exception as e:
            logger.warning(f"Failed to create banter thread for clip {msg.id}: {e}")

    def _schedule_ingest_panel_bump(self, channel: discord.TextChannel) -> None:
        asyncio.create_task(self._refresh_ingest_panel(channel))

    # --------------------------------------------------------------------------
    # GALLERY POST
    # --------------------------------------------------------------------------
    def _build_clip_embed(
        self,
        author: discord.User | discord.Member,
        *,
        url: str | None = None,
        thumbnail: str | None = None,
        video_attached: bool = False,
    ) -> discord.Embed:
        """PC upload — author bar; Discord renders the attached MP4 below."""
        embed = discord.Embed(color=THEME_PRIMARY)
        if not video_attached:
            if url:
                embed.url = url
            if thumbnail:
                embed.set_image(url=thumbnail)
        embed.set_author(
            name=author.display_name,
            icon_url=author.display_avatar.url if author.display_avatar else None,
        )
        return embed

    async def _finalize_clip_post(
        self,
        channel: discord.TextChannel,
        title: str,
        author: discord.User | discord.Member,
        *,
        embed: discord.Embed | None = None,
        url: str | None = None,
        thumbnail: str | None = None,
        source: str = "link",
        file: discord.File | None = None,
        content: str | None = None,
        reply_interaction: discord.Interaction | None = None,
        reply_channel: discord.abc.Messageable | None = None,
        cleanup_user_message: discord.Message | None = None,
    ):
        try:
            kwargs: dict = {}
            if content:
                kwargs["content"] = content
            if embed is not None:
                kwargs["embed"] = embed
            if file:
                kwargs["file"] = file
            msg = await channel.send(**kwargs)
        except Exception as e:
            logger.error(f"Failed to post clip embed: {e}")
            err = "❌ Failed to post your clip. Try again shortly."
            if reply_interaction:
                await safe_reply(reply_interaction, err, ephemeral=True)
            elif reply_channel:
                try:
                    await reply_channel.send(err)
                except Exception:
                    pass
            return None

        asyncio.create_task(self._create_banter_thread(msg, author, title))

        self.data["clips"][str(msg.id)] = {
            "title": title,
            "url": url,
            "author_id": author.id,
            "thumbnail": thumbnail,
            "source": source,
        }
        self._save()

        self._schedule_ingest_panel_bump(channel)

        await self._flow_cleanup(
            author.id,
            dm_channel=reply_channel if isinstance(reply_channel, discord.DMChannel) else None,
            user_message=cleanup_user_message,
        )
        if reply_interaction:
            try:
                await reply_interaction.followup.send(
                    f"✅ Posted to {channel.mention}",
                    ephemeral=True,
                    delete_after=8,
                )
            except Exception:
                pass
        return msg

    async def publish_clip(self, interaction: discord.Interaction, url: str):
        user = interaction.user
        gid = user.guild.id if isinstance(user, discord.Member) and user.guild else SHADOW_MAIN_GUILD_ID
        channel = await self._clips_channel(guild_id=gid)
        if channel is None:
            return await safe_reply(
                interaction,
                "❌ Clips channel is unavailable. Tell an admin.",
                ephemeral=True,
            )

        if _is_valid_youtube_url(url):
            title, thumbnail = await self._fetch_youtube_metadata(url)
            await self._finalize_clip_post(
                channel,
                title,
                interaction.user,
                url=url,
                thumbnail=thumbnail,
                source="youtube",
                content=url,
                reply_interaction=interaction,
            )
            return

        title, thumbnail = await self._fetch_medal_link_metadata(url)
        # URL only — custom embeds block Discord's native Medal/YouTube video unfurl.
        await self._finalize_clip_post(
            channel,
            title,
            interaction.user,
            url=url,
            thumbnail=thumbnail,
            source="medal",
            content=url,
            reply_interaction=interaction,
        )

    async def publish_clip_file(
        self,
        author: discord.User | discord.Member,
        attachment: discord.Attachment,
        reply_channel: discord.abc.Messageable,
        *,
        user_message: discord.Message | None = None,
    ):
        gid = author.guild.id if isinstance(author, discord.Member) and author.guild else SHADOW_MAIN_GUILD_ID
        channel = await self._clips_channel(guild_id=gid)
        if channel is None:
            await reply_channel.send("❌ Clips channel is unavailable. Tell an admin.")
            return

        guild = channel.guild or await self._resolve_guild()
        max_bytes = self._upload_limit_bytes(guild)

        content_type = (attachment.content_type or "").split(";")[0].strip().lower()
        if content_type and content_type not in UPLOAD_VIDEO_TYPES:
            await reply_channel.send("❌ Send a video file (`mp4`, `webm`, `mov`).")
            return

        title = Path(attachment.filename or "clip").stem[:80] or "Uploaded Clip"
        embed = self._build_clip_embed(author, video_attached=True)

        try:
            if attachment.size > max_bytes:
                raw = await attachment.read()
                fitted = await self._ffmpeg_fit_to_cap(raw, max_bytes)
                if not fitted:
                    await reply_channel.send(
                        f"❌ Too large (**{_format_mb(attachment.size)}MB**) and couldn't compress "
                        f"to fit the **{_format_mb(max_bytes)}MB** server cap."
                    )
                    return
                clip_file = discord.File(io.BytesIO(fitted), filename="clip.mp4", spoiler=False)
            else:
                clip_file = await attachment.to_file()
        except Exception as e:
            logger.error(f"Failed to read attachment {attachment.id}: {e}")
            await reply_channel.send("❌ Could not read that file. Try again.")
            return

        await self._finalize_clip_post(
            channel,
            title,
            author,
            embed=embed,
            source="upload",
            file=clip_file,
            reply_channel=reply_channel,
            cleanup_user_message=user_message,
        )

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        sess = self._flow_sessions.get(message.author.id)
        if not sess or not sess.get("upload_pending"):
            return

        is_dm = isinstance(message.channel, discord.DMChannel)
        is_upload_thread = (
            sess.get("upload_thread_id") is not None
            and message.channel.id == sess.get("upload_thread_id")
        )
        if not (is_dm or is_upload_thread):
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
            logger.error(f"Clip upload failed for {message.author.id}: {e}")
            await message.channel.send("❌ Upload failed.", delete_after=8)

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
        gid = channel.guild.id if channel.guild else SHADOW_MAIN_GUILD_ID
        await self._delete_ingest_panel(channel, self._panel_id(gid))

        view = SubmitClipPanelView()
        try:
            panel_msg = await channel.send(embed=self._build_ingest_panel_embed(), view=view)
            self.bot.add_view(view)
            self._set_panel_id(gid, panel_msg.id)
            self._save()
            logger.info(f"Ingest panel refreshed ({panel_msg.id}) guild {gid}.")
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
    async def _purge_hof_threads(self, channel: discord.TextChannel) -> int:
        """Hall of Fame is retired — delete any stray HOF threads under the gallery."""
        removed = 0
        try:
            for thread in list(channel.threads):
                if thread.name == HOF_THREAD_NAME:
                    try:
                        await thread.delete()
                        removed += 1
                    except Exception as e:
                        logger.warning(f"Could not delete stale HOF thread {thread.id}: {e}")
            async for thread in channel.archived_threads(limit=100):
                if thread.name == HOF_THREAD_NAME:
                    try:
                        await thread.delete()
                        removed += 1
                    except Exception as e:
                        logger.warning(f"Could not delete archived HOF thread {thread.id}: {e}")
        except Exception as e:
            logger.warning(f"HOF thread purge sweep failed: {e}")
        if removed:
            logger.info(f"Purged {removed} stale Hall of Fame thread(s).")
        return removed

    @discord.slash_command(
        name="clips_deploy",
        description="Deploy the clips ingest panel and lock the gallery.",
        guild_ids=REGISTERED_GUILD_IDS,
        default_member_permissions=discord.Permissions(administrator=True),
    )
    async def clips_deploy(self, ctx: discord.ApplicationContext):
        if not has_admin_shadow(ctx.author, ctx.guild.id if ctx.guild else None):
            return await safe_reply(ctx, "🚫 Admin clearance required.", ephemeral=True)

        await safe_reply(ctx, "🛠️ Deploying clips system...", ephemeral=True)

        channel = await self._clips_channel(ctx.guild.id)
        if channel is None:
            return await safe_reply(ctx, "❌ Clips channel unavailable.", ephemeral=True)

        try:
            cid = ch_id(ctx.guild.id, "clips")
            if cid:
                channel = await ctx.guild.fetch_channel(cid)
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
        except Exception as e:
            logger.error(f"Failed to deploy ingest panel: {e}")
            return await safe_reply(ctx, f"❌ Failed to deploy ingest panel: {e}", ephemeral=True)

        purged = await self._purge_hof_threads(channel)
        self._save()

        await safe_reply(
            ctx,
            f"✅ Clips live in {channel.mention}.\n"
            f"• {perm_status}\n"
            f"• Panel ID `{self._panel_id(ctx.guild.id)}`\n"
            f"• Stale Hall of Fame threads removed: **{purged}**",
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
