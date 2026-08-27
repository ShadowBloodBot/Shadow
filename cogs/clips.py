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
from urllib.parse import quote

import aiohttp
import discord
from discord.ext import commands

logger = logging.getLogger("ShadowSyn.Clips")

from cogs.clip_urls import (
    clip_source,
    extract_og,
    extract_urls,
    html_looks_like_video,
    is_allowlisted_clip_url,
    is_https_url,
    medal_content_id,
    normalize_clip_url as _normalize_clip_url,
    youtube_id as _youtube_id,
)
from cogs.guild_registry import (
    PERSIST_ROOT,
    REGISTERED_GUILD_IDS,
    SHADOW_MAIN_GUILD_ID,
    ch_id,
    has_admin_shadow,
    is_registered_guild,
    resolve_channel,
    resolve_role,
    role_id,
)
from cogs.utils import safe_reply

# ==============================================================================
# CONSTANTS & IDS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
OWNER_ID = 482463400929263627
INGEST_PANEL_TITLE = "🎬 Clips"
INGEST_PANEL_DESCRIPTION = "Drop a clip — link or video file."
INGEST_PANEL_FOOTER_PREFIX = "ShadowSyn Clips · "
HOF_THREAD_NAME = "🏛️ Hall of Fame"
CLIP_REACT = "🔥"
CHATTER_HINT = "This channel is clips only — react on the post."

MEDAL_API_KEY = os.getenv("MEDAL_API_KEY")

UA_HEADERS = {"User-Agent": "ShadowSyn/1.0 (+https://medal.tv)"}
METADATA_TIMEOUT = aiohttp.ClientTimeout(total=8)
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
_CONTRIBUTOR_NAME_MAX = 24


def _total_clips(clips_data: dict) -> int:
    return len(clips_data.get("clips") or {})


def _contributor_counts(clips_data: dict) -> dict[int, int]:
    counts: dict[int, int] = {}
    for clip in (clips_data.get("clips") or {}).values():
        raw_id = clip.get("author_id")
        if raw_id is None:
            continue
        try:
            author_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        counts[author_id] = counts.get(author_id, 0) + 1
    return counts


def _top_contributor_ids(clips_data: dict) -> list[int]:
    counts = _contributor_counts(clips_data)
    if not counts:
        return []
    max_count = max(counts.values())
    return sorted(author_id for author_id, count in counts.items() if count == max_count)


def _author_name_from_clips(clips_data: dict, author_id: int) -> str | None:
    for clip in (clips_data.get("clips") or {}).values():
        try:
            if int(clip.get("author_id", 0)) != author_id:
                continue
        except (TypeError, ValueError):
            continue
        name = clip.get("author_name")
        if name:
            return str(name)
    return None


def _truncate_contributor_name(name: str) -> str:
    name = name.strip()
    if len(name) <= _CONTRIBUTOR_NAME_MAX:
        return name
    return name[: _CONTRIBUTOR_NAME_MAX - 1].rstrip() + "…"


def _cached_top_contributor_names(clips_data: dict) -> list[str]:
    names: list[str] = []
    for author_id in _top_contributor_ids(clips_data):
        name = _author_name_from_clips(clips_data, author_id)
        if name:
            names.append(_truncate_contributor_name(name))
    return sorted(names, key=str.casefold)


def _ingest_panel_footer(clips_data: dict, contributor_names: list[str] | None = None) -> str:
    total = _total_clips(clips_data)
    if total <= 0:
        return "ShadowSyn"
    text = f"{INGEST_PANEL_FOOTER_PREFIX}{total:,} clips shared"
    if not contributor_names:
        return text
    if len(contributor_names) == 1:
        return f"{text} [Top Contributor: {contributor_names[0]}]"
    joined = ", ".join(contributor_names)
    return f"{text} [Top Contributors: {joined}]"


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


def _is_video_attachment(attachment: discord.Attachment) -> bool:
    content_type = (attachment.content_type or "").split(";")[0].strip().lower()
    if content_type in UPLOAD_VIDEO_TYPES:
        return True
    name = (attachment.filename or "").lower()
    return name.endswith((".mp4", ".webm", ".mov", ".mkv", ".avi"))


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
        content_id = medal_content_id(_normalize_clip_url(url))
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

        content_id = medal_content_id(clean)
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
                    title = extract_og(html, "og:title") or extract_og(html, "twitter:title")
                if not thumbnail:
                    thumbnail = extract_og(html, "og:image") or extract_og(html, "twitter:image")
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

        try:
            await msg.add_reaction(CLIP_REACT)
        except Exception as e:
            logger.warning(f"Could not seed clip reaction on {msg.id}: {e}")

        self.data["clips"][str(msg.id)] = {
            "title": title,
            "url": url,
            "author_id": author.id,
            "author_name": getattr(author, "display_name", None) or str(author),
            "thumbnail": thumbnail,
            "source": source,
        }
        self._save()

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

    async def _fetch_html(self, url: str) -> str | None:
        session = await self._get_session()
        try:
            async with session.get(
                url, headers=UA_HEADERS, allow_redirects=True, timeout=METADATA_TIMEOUT
            ) as resp:
                if resp.status != 200:
                    return None
                return await resp.text()
        except Exception as e:
            logger.warning(f"HTML fetch failed for {url}: {e}")
            return None

    async def is_clip_url(self, url: str) -> bool:
        url = _normalize_clip_url(url)
        if is_allowlisted_clip_url(url):
            return True
        if not is_https_url(url):
            return False
        html = await self._fetch_html(url)
        return bool(html and html_looks_like_video(html))

    async def _fetch_link_metadata(self, url: str, source: str) -> tuple[str, str | None]:
        fallback = f"{source.replace('_', ' ').title()} Clip"
        html = await self._fetch_html(url)
        if not html:
            return fallback, None
        title = extract_og(html, "og:title") or extract_og(html, "twitter:title")
        thumbnail = extract_og(html, "og:image") or extract_og(html, "twitter:image")
        if title:
            title = title[:80]
        return title or fallback, thumbnail

    async def _reject_chatter(self, message: discord.Message, hint: str | None = None) -> None:
        try:
            await message.delete()
        except Exception:
            return
        text = hint or CHATTER_HINT
        try:
            await message.channel.send(
                f"{message.author.mention} {text}",
                delete_after=8,
            )
        except Exception:
            pass

    def _is_clips_parent(self, message: discord.Message) -> bool:
        channel = message.channel
        if isinstance(channel, discord.Thread):
            return False
        if not isinstance(channel, discord.TextChannel) or channel.guild is None:
            return False
        clips_id = ch_id(channel.guild.id, "clips")
        return bool(clips_id) and channel.id == clips_id

    async def publish_clip(
        self,
        url: str,
        author: discord.User | discord.Member,
        *,
        reply_interaction: discord.Interaction | None = None,
        reply_channel: discord.abc.Messageable | None = None,
        cleanup_user_message: discord.Message | None = None,
    ):
        gid = SHADOW_MAIN_GUILD_ID
        if cleanup_user_message and cleanup_user_message.guild:
            gid = cleanup_user_message.guild.id
        elif isinstance(author, discord.Member) and author.guild:
            gid = author.guild.id
        elif reply_interaction and reply_interaction.guild:
            gid = reply_interaction.guild.id

        channel = await self._clips_channel(guild_id=gid)
        if channel is None:
            err = "❌ Clips channel is unavailable. Tell an admin."
            if reply_interaction:
                return await safe_reply(reply_interaction, err, ephemeral=True)
            if reply_channel:
                try:
                    await reply_channel.send(err)
                except Exception:
                    pass
            return None

        source = clip_source(url)
        if source == "youtube":
            title, thumbnail = await self._fetch_youtube_metadata(url)
        elif source == "medal":
            title, thumbnail = await self._fetch_medal_link_metadata(url)
        else:
            title, thumbnail = await self._fetch_link_metadata(url, source)

        # URL only — custom embeds block Discord's native video unfurl.
        return await self._finalize_clip_post(
            channel,
            title,
            author,
            url=url,
            thumbnail=thumbnail,
            source=source,
            content=url,
            reply_interaction=reply_interaction,
            reply_channel=reply_channel,
            cleanup_user_message=cleanup_user_message,
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
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_upload_thread = bool(
            sess
            and sess.get("upload_thread_id") is not None
            and message.channel.id == sess.get("upload_thread_id")
        )
        if sess and sess.get("upload_pending") and (is_dm or is_upload_thread):
            if not message.attachments:
                await message.channel.send("📎 Attach a video file.", delete_after=8)
                return
            videos = [a for a in message.attachments if _is_video_attachment(a)]
            if not videos:
                await message.channel.send("❌ Send a video file (`mp4`, `webm`, `mov`).", delete_after=8)
                return
            if len(videos) > 1:
                await message.channel.send("❌ One file only.", delete_after=8)
                return
            try:
                await self.publish_clip_file(
                    message.author,
                    videos[0],
                    message.channel,
                    user_message=message,
                )
            except Exception as e:
                logger.error(f"Clip upload failed for {message.author.id}: {e}")
                await message.channel.send("❌ Upload failed.", delete_after=8)
            return

        if not self._is_clips_parent(message):
            return

        videos = [a for a in message.attachments if _is_video_attachment(a)]
        if videos:
            if len(videos) > 1:
                await message.channel.send("❌ One video file only.", delete_after=8)
                return
            try:
                await self.publish_clip_file(
                    message.author,
                    videos[0],
                    message.channel,
                    user_message=message,
                )
            except Exception as e:
                logger.error(f"Clip drop-in upload failed for {message.author.id}: {e}")
                await message.channel.send("❌ Upload failed.", delete_after=8)
            return

        if message.attachments:
            await self._reject_chatter(message, "Send a video file (`mp4`, `webm`, `mov`).")
            return

        urls = extract_urls(message.content)
        if urls:
            chosen = None
            for candidate in urls:
                if await self.is_clip_url(candidate):
                    chosen = candidate
                    break
            if chosen:
                try:
                    await self.publish_clip(
                        chosen,
                        message.author,
                        reply_channel=message.channel,
                        cleanup_user_message=message,
                    )
                except Exception as e:
                    logger.error(f"Clip drop-in link failed for {message.author.id}: {e}")
                    await message.channel.send("❌ Could not post that clip.", delete_after=8)
                return
            await self._reject_chatter(message, "That link isn't a clip I can share.")
            return

        await self._reject_chatter(message)

    # --------------------------------------------------------------------------
    # INGEST PANEL
    # --------------------------------------------------------------------------
    async def _resolve_contributor_name(self, author_id: int) -> str:
        name = _author_name_from_clips(self.data, author_id)
        if name:
            return _truncate_contributor_name(name)
        try:
            user = await self.bot.fetch_user(author_id)
            return _truncate_contributor_name(user.display_name or user.name)
        except Exception:
            return "Unknown"

    async def _build_ingest_panel_embed(self) -> discord.Embed:
        contributor_names: list[str] = []
        for author_id in _top_contributor_ids(self.data):
            contributor_names.append(await self._resolve_contributor_name(author_id))
        contributor_names.sort(key=str.casefold)

        embed = discord.Embed(
            title=INGEST_PANEL_TITLE,
            description=INGEST_PANEL_DESCRIPTION,
            color=THEME_PRIMARY,
        )
        embed.set_footer(
            text=_ingest_panel_footer(
                self.data,
                contributor_names if _total_clips(self.data) > 0 else None,
            )
        )
        return embed

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

    async def _purge_ingest_panels(self, channel: discord.TextChannel) -> None:
        """Remove every ingest panel in channel (pinned or not)."""
        removed: set[int] = set()
        try:
            pinned = await channel.pins()
            for msg in pinned:
                if not msg.embeds or msg.embeds[0].title != INGEST_PANEL_TITLE:
                    continue
                if msg.id in removed:
                    continue
                try:
                    await msg.unpin()
                except Exception:
                    pass
                await msg.delete()
                removed.add(msg.id)
        except Exception as e:
            logger.warning(f"Could not scan pins for ingest panels: {e}")

        try:
            async for msg in channel.history(limit=100):
                if msg.id in removed:
                    continue
                if not msg.embeds or msg.embeds[0].title != INGEST_PANEL_TITLE:
                    continue
                try:
                    await msg.delete()
                    removed.add(msg.id)
                except Exception as e:
                    logger.warning(f"Could not delete ingest panel {msg.id}: {e}")
        except Exception as e:
            logger.warning(f"Could not scan history for ingest panels: {e}")

    async def _refresh_ingest_panel(self, channel: discord.TextChannel):
        gid = channel.guild.id if channel.guild else SHADOW_MAIN_GUILD_ID
        await self._purge_ingest_panels(channel)
        await self._delete_ingest_panel(channel, self._panel_id(gid))

        try:
            panel_msg = await channel.send(embed=await self._build_ingest_panel_embed())
            try:
                await panel_msg.pin()
            except Exception as e:
                logger.warning(f"Could not pin clips header {panel_msg.id}: {e}")
            try:
                async for notice in channel.history(limit=8):
                    if notice.type == discord.MessageType.pins_add:
                        await notice.delete()
            except Exception as e:
                logger.warning(f"Could not delete clips pin notice: {e}")
            self._set_panel_id(gid, panel_msg.id)
            self._save()
            logger.info(f"Clips header pinned ({panel_msg.id}) guild {gid}.")
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

        reason = "ShadowSyn clips: cinema gallery (drop clips, react, no chat)"
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
                ow.send_messages = True
                ow.embed_links = True
                ow.attach_files = True
                ow.create_public_threads = False
                ow.create_private_threads = False
                ow.send_messages_in_threads = True
                await channel.set_permissions(target, overwrite=ow, reason=reason)
                updated += 1
            logger.info(f"Gallery drop-in permissions set for {updated} target(s) in {channel.id}.")
            return True, f"Drop-in posting enabled for **{updated}** permission target(s)."
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

    async def _archive_gallery_threads(self, channel: discord.TextChannel) -> int:
        """Sidebar cleanup — archive leftover clip banter threads. Keep clip messages."""
        archived = 0
        try:
            for thread in list(channel.threads):
                try:
                    await thread.edit(archived=True, locked=True, reason="Cinema clips gallery")
                    archived += 1
                except Exception as e:
                    logger.warning(f"Could not archive clips thread {thread.id}: {e}")
        except Exception as e:
            logger.warning(f"Clips thread archive sweep failed: {e}")
        if archived:
            logger.info(f"Archived {archived} leftover clips thread(s).")
        return archived

    @discord.slash_command(
        name="clips_deploy",
        description="Deploy the clips cinema header.",
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
        archived = await self._archive_gallery_threads(channel)
        self._save()

        await safe_reply(
            ctx,
            f"✅ Clips live in {channel.mention}.\n"
            f"• {perm_status}\n"
            f"• Header ID `{self._panel_id(ctx.guild.id)}`\n"
            f"• Stale Hall of Fame threads removed: **{purged}**\n"
            f"• Leftover clip threads archived: **{archived}**",
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
