# cogs/music.py
import asyncio
import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import discord
import yt_dlp
from discord import Option, SelectOption
from discord.ext import commands
from discord.ui import View, Button, Select

from cogs.guild_registry import REGISTERED_GUILD_IDS, is_owner, role_id

# ==============================================================================
# TELEMETRY
# ==============================================================================
logger = logging.getLogger("ShadowSyn.Music")

# ==============================================================================
# CONSTANTS
# ==============================================================================
THEME_PRIMARY = 0x2B0B35
AUTO_LEAVE_TIMEOUT = 120
VOICE_SETTLE_MAX = 0.5
SEARCH_RESULTS = 5

FFMPEG_BEFORE = "-probesize 32 -analyzeduration 0"
FFMPEG_OPTIONS = "-loglevel error"

YOUTUBE_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:"
    r"youtube\.com/watch\?[^\s]*v=[\w-]{11}[^\s]*"
    r"|youtu\.be/[\w-]{11}(?:\?[^\s]*)?"
    r"|youtube\.com/shorts/[\w-]{11}(?:\?[^\s]*)?"
    r")",
    re.I,
)
SPOTIFY_URL_RE = re.compile(
    r"https?://open\.spotify\.com/(?:track|album|playlist)/[A-Za-z0-9]+(?:\?[^\s]*)?",
    re.I,
)
URL_IN_TEXT_RE = re.compile(
    r"https?://(?:www\.)?(?:"
    r"youtube\.com/[^\s]+"
    r"|youtu\.be/[^\s]+"
    r"|open\.spotify\.com/[^\s]+"
    r")",
    re.I,
)

YDL_OPTS_BASE = {
    "format": "bestaudio[acodec=opus]/bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": False,
    "default_search": "ytsearch1",
    "socket_timeout": 15,
    "retries": 2,
    "fragment_retries": 2,
    "extract_flat": False,
    "skip_download": True,
    "extractor_args": {"youtube": {"player_client": ["android", "web"]}},
}


@dataclass
class Track:
    title: str
    url: str
    webpage_url: str
    duration: Optional[int]
    requester_id: int
    requester_name: str
    thumbnail: Optional[str] = None


@dataclass
class GuildPlayer:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    current: Optional[Track] = None
    worker: Optional[asyncio.Task] = None
    leave_timer: Optional[asyncio.Task] = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


def has_music_role(user) -> bool:
    if is_owner(user):
        return True
    if not isinstance(user, discord.Member):
        return False
    rid = role_id(user.guild.id, "member")
    if rid is None:
        return False
    return any(r.id == rid for r in user.roles)


def _format_duration(seconds: Optional[int]) -> str:
    if not seconds or seconds <= 0:
        return "?:??"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _pick_thumbnail(entry: dict) -> Optional[str]:
    thumb = entry.get("thumbnail")
    if thumb:
        return thumb
    thumbs = entry.get("thumbnails")
    if thumbs:
        return thumbs[-1].get("url")
    return None


def _extract_urls(text: str) -> list[str]:
    found: list[str] = []
    for match in URL_IN_TEXT_RE.finditer(text):
        url = match.group(0).rstrip(">).,]")
        if YOUTUBE_URL_RE.search(url) or SPOTIFY_URL_RE.search(url):
            found.append(url)
    return found


def _is_url_query(query: str) -> bool:
    return bool(_extract_urls(query))


def _normalize_query(query: str) -> str:
    urls = _extract_urls(query)
    if urls:
        return urls[0]
    return query.strip()


def _ydl_extract(url_or_search: str, *, playlist: bool = True) -> list[dict]:
    opts = {**YDL_OPTS_BASE, "noplaylist": not playlist}
    with yt_dlp.YoutubeDL(opts) as ydl:
        if not url_or_search.startswith(("http://", "https://", "ytsearch")):
            url_or_search = f"ytsearch1:{url_or_search}"
        info = ydl.extract_info(url_or_search, download=False)
    if not info:
        return []

    if info.get("_type") == "playlist" or info.get("entries"):
        return [e for e in (info.get("entries") or []) if e]

    return [info]


def _ydl_search_candidates(query: str, limit: int = SEARCH_RESULTS) -> list[dict]:
    opts = {
        **YDL_OPTS_BASE,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "noplaylist": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{limit}:{query.strip()}", download=False)
    return [e for e in (info.get("entries") or []) if e and e.get("title")]


def _entry_to_track(entry: dict, requester_id: int, requester_name: str) -> Optional[Track]:
    if not entry:
        return None
    stream_url = entry.get("url")
    if not stream_url:
        return None
    title = entry.get("title") or "Unknown"
    webpage = entry.get("webpage_url") or entry.get("original_url") or entry.get("url") or stream_url
    return Track(
        title=title,
        url=stream_url,
        webpage_url=webpage,
        duration=entry.get("duration"),
        requester_id=requester_id,
        requester_name=requester_name,
        thumbnail=_pick_thumbnail(entry),
    )


def _status_line(position: int, track_count: int) -> str:
    if position == 0:
        status = "▶️ Playing now"
    else:
        status = f"📋 Queued — position **#{position + 1}**"
    if track_count > 1:
        status += f" · **{track_count} tracks** added"
    return status


# ==============================================================================
# UI — search picker + transport controls
# ==============================================================================
class SearchPickSelect(Select):
    def __init__(
        self,
        cog: "MusicCog",
        guild: discord.Guild,
        channel: discord.VoiceChannel,
        requester: discord.Member,
        candidates: list[dict],
    ):
        self.cog = cog
        self.guild = guild
        self.channel = channel
        self.requester = requester
        self.candidates = candidates

        options = []
        for i, entry in enumerate(candidates[:SEARCH_RESULTS]):
            title = (entry.get("title") or "Unknown")[:100]
            duration = _format_duration(entry.get("duration"))
            options.append(
                SelectOption(
                    label=title,
                    description=f"{duration} · tap to play",
                    value=str(i),
                )
            )

        super().__init__(
            placeholder="Pick the right track…",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if not has_music_role(interaction.user):
            return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        entry = self.candidates[int(self.values[0])]
        target = entry.get("url") or entry.get("webpage_url")
        if not target:
            return await interaction.followup.send("❌ That result expired — try `/play` again.", ephemeral=True)

        try:
            tracks = await self.cog._resolve_tracks(
                target,
                self.requester.id,
                self.requester.display_name,
            )
            position = await self.cog._enqueue(self.guild, self.channel, tracks)
        except Exception as exc:
            logger.error("Search pick failed: %s", exc)
            return await interaction.followup.send(f"❌ Could not play that: {exc}", ephemeral=True)

        first = tracks[0]
        title = "🎵 Now Playing" if position == 0 else "📋 Added to Queue"
        embed = self.cog._track_embed(
            first,
            title=title,
            status=_status_line(position, len(tracks)),
        )
        view = MusicControlsView(self.cog, self.guild.id)
        await interaction.followup.send("✅ Added to queue.", ephemeral=True)
        await interaction.channel.send(embed=embed, view=view)


class SearchPickView(View):
    def __init__(
        self,
        cog: "MusicCog",
        guild: discord.Guild,
        channel: discord.VoiceChannel,
        requester: discord.Member,
        candidates: list[dict],
    ):
        super().__init__(timeout=60)
        self.add_item(SearchPickSelect(cog, guild, channel, requester, candidates))


class MusicControlsView(View):
    def __init__(self, cog: "MusicCog", guild_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id

    async def _access_check(self, interaction: discord.Interaction) -> bool:
        member = interaction.guild.get_member(interaction.user.id) if interaction.guild else None
        if not has_music_role(member):
            await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
            return False
        if not member or not getattr(member, "voice", None) or not member.voice.channel:
            await interaction.response.send_message("❌ Join a voice channel first.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Pause", style=discord.ButtonStyle.secondary, emoji="⏸️", row=0)
    async def pause_btn(self, button: Button, interaction: discord.Interaction):
        if not await self._access_check(interaction):
            return
        vc = interaction.guild.voice_client
        if not vc:
            return await interaction.response.send_message("❌ Not connected.", ephemeral=True)
        if vc.is_paused():
            vc.resume()
            button.label = "Pause"
            button.emoji = "⏸️"
            return await interaction.response.edit_message(view=self)
        if not vc.is_playing():
            return await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)
        vc.pause()
        button.label = "Resume"
        button.emoji = "▶️"
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Skip", style=discord.ButtonStyle.primary, emoji="⏭️", row=0)
    async def skip_btn(self, button: Button, interaction: discord.Interaction):
        if not await self._access_check(interaction):
            return
        vc = interaction.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await interaction.response.send_message("❌ Nothing is playing.", ephemeral=True)
        player = self.cog._get_player(interaction.guild.id)
        skipped = player.current.title if player.current else "track"
        vc.stop()
        await interaction.response.send_message(f"⏭️ Skipped **{skipped}**", ephemeral=True)

    @discord.ui.button(label="Queue", style=discord.ButtonStyle.secondary, emoji="📋", row=0)
    async def queue_btn(self, button: Button, interaction: discord.Interaction):
        if not has_music_role(interaction.user):
            return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        embed = self.cog._queue_embed(interaction.guild.id)
        if not embed:
            return await interaction.response.send_message("📭 Queue is empty.", ephemeral=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class MusicCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}

    def _get_player(self, guild_id: int) -> GuildPlayer:
        if guild_id not in self.players:
            self.players[guild_id] = GuildPlayer()
        return self.players[guild_id]

    def is_active(self, guild_id: int) -> bool:
        """True while music is playing or has tracks queued — TTS must yield."""
        guild = self.bot.get_guild(guild_id)
        if guild and guild.voice_client and guild.voice_client.is_paused():
            return True

        player = self.players.get(guild_id)
        if not player:
            return False
        if player.current or not player.queue.empty():
            return True
        if player.worker and not player.worker.done():
            return True
        return False

    async def _interrupt_tts(self, guild: discord.Guild):
        tts = self.bot.get_cog("TTSCog")
        if tts:
            await tts.interrupt(guild)

    async def _ensure_voice(self, guild: discord.Guild, channel: discord.VoiceChannel):
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            vc = await channel.connect(timeout=20.0)
            elapsed = 0.0
            while elapsed < VOICE_SETTLE_MAX:
                await asyncio.sleep(0.1)
                elapsed += 0.1
                if vc.is_connected():
                    break
        elif vc.channel.id != channel.id:
            await vc.move_to(channel)
        if not vc.is_connected():
            raise RuntimeError("Voice connection failed")
        return vc

    def _cancel_leave_timer(self, player: GuildPlayer):
        if player.leave_timer and not player.leave_timer.done():
            player.leave_timer.cancel()
        player.leave_timer = None

    async def _schedule_leave(self, guild: discord.Guild):
        await asyncio.sleep(AUTO_LEAVE_TIMEOUT)
        player = self.players.get(guild.id)
        vc = guild.voice_client
        if (
            vc
            and vc.is_connected()
            and not vc.is_playing()
            and not vc.is_paused()
            and player
            and player.queue.empty()
            and player.current is None
        ):
            await vc.disconnect()
            logger.info("Auto-disconnected from %s (idle).", guild.name)

    async def _resolve_tracks(
        self, query: str, requester_id: int, requester_name: str
    ) -> list[Track]:
        normalized = _normalize_query(query)
        is_search = not _is_url_query(query)
        is_playlist = bool(
            SPOTIFY_URL_RE.search(normalized)
            and ("/playlist/" in normalized or "/album/" in normalized)
        ) or ("list=" in normalized and "youtube.com" in normalized)

        def extract():
            entries = _ydl_extract(normalized, playlist=is_playlist or not is_search)
            tracks = []
            for entry in entries:
                track = _entry_to_track(entry, requester_id, requester_name)
                if track:
                    tracks.append(track)
            return tracks

        return await self.bot.loop.run_in_executor(None, extract)

    async def _search_candidates(self, query: str) -> list[dict]:
        def search():
            return _ydl_search_candidates(query)

        return await self.bot.loop.run_in_executor(None, search)

    async def _play_track(self, guild: discord.Guild, track: Track):
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            return

        source = discord.FFmpegOpusAudio(
            track.url,
            before_options=FFMPEG_BEFORE,
            options=FFMPEG_OPTIONS,
        )
        done = asyncio.Event()

        def after_play(error):
            if error:
                logger.error("Playback error in %s: %s", guild.name, error)
            self.bot.loop.call_soon_threadsafe(done.set)

        vc.play(source, after=after_play)
        await done.wait()

    async def _worker(self, guild: discord.Guild):
        player = self._get_player(guild.id)
        try:
            while True:
                try:
                    track = await asyncio.wait_for(player.queue.get(), timeout=0.1)
                except asyncio.TimeoutError:
                    if player.queue.empty():
                        break
                    continue

                player.current = track
                vc = guild.voice_client
                if not vc or not vc.is_connected():
                    player.queue.task_done()
                    continue

                try:
                    await self._play_track(guild, track)
                except Exception as exc:
                    logger.error("Failed to play %s: %s", track.title, exc)
                finally:
                    player.current = None
                    player.queue.task_done()
        finally:
            player.worker = None
            vc = guild.voice_client
            if player.queue.empty() and (not vc or (not vc.is_playing() and not vc.is_paused())):
                self._cancel_leave_timer(player)
                player.leave_timer = asyncio.create_task(self._schedule_leave(guild))

    async def _enqueue(
        self,
        guild: discord.Guild,
        channel: discord.VoiceChannel,
        tracks: list[Track],
    ) -> int:
        if not tracks:
            raise RuntimeError("No playable tracks found.")

        player = self._get_player(guild.id)
        self._cancel_leave_timer(player)

        async with player.lock:
            await self._interrupt_tts(guild)
            await self._ensure_voice(guild, channel)
            position_before = player.queue.qsize() + (1 if player.current else 0)
            for track in tracks:
                await player.queue.put(track)

            if player.worker is None or player.worker.done():
                player.worker = asyncio.create_task(self._worker(guild))

        return position_before

    def _track_embed(self, track: Track, *, title: str, status: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=f"**[{track.title}]({track.webpage_url})**",
            color=THEME_PRIMARY,
            url=track.webpage_url,
        )
        embed.add_field(name="Length", value=_format_duration(track.duration), inline=True)
        embed.add_field(name="Requested by", value=track.requester_name, inline=True)
        if track.thumbnail:
            embed.set_thumbnail(url=track.thumbnail)
        embed.set_footer(text=status)
        return embed

    def _queue_embed(self, guild_id: int) -> Optional[discord.Embed]:
        player = self._get_player(guild_id)
        lines = []
        total_seconds = 0

        if player.current:
            lines.append(f"**▶️ Now** · [{player.current.title}]({player.current.webpage_url})")
            if player.current.duration:
                total_seconds += player.current.duration

        pending = list(player.queue._queue)  # noqa: SLF001
        if pending:
            for i, track in enumerate(pending[:10], start=1):
                dur = _format_duration(track.duration)
                lines.append(f"`{i}.` [{track.title}]({track.webpage_url}) · `{dur}` — *{track.requester_name}*")
                if track.duration:
                    total_seconds += track.duration
            if len(pending) > 10:
                lines.append(f"*…and {len(pending) - 10} more*")

        if not lines:
            return None

        embed = discord.Embed(
            title="📋 Queue",
            description="\n".join(lines),
            color=THEME_PRIMARY,
        )
        if total_seconds:
            embed.set_footer(text=f"~{_format_duration(total_seconds)} total remaining")
        return embed

    async def _require_music_access(
        self, ctx: discord.ApplicationContext
    ) -> Optional[discord.VoiceChannel]:
        if not has_music_role(ctx.author):
            await ctx.respond("⛔ Restricted.", ephemeral=True)
            return None
        member = ctx.guild.get_member(ctx.author.id)
        if not member or not getattr(member, "voice", None) or not member.voice.channel:
            await ctx.respond("❌ Join a voice channel first.", ephemeral=True)
            return None
        return member.voice.channel

    def _play_payload(self, guild_id: int, tracks: list[Track], position: int) -> tuple[discord.Embed, MusicControlsView]:
        first = tracks[0]
        title = "🎵 Now Playing" if position == 0 else "📋 Added to Queue"
        embed = self._track_embed(first, title=title, status=_status_line(position, len(tracks)))
        return embed, MusicControlsView(self, guild_id)

    # -------------------------------------------------------------------------
    # /play
    # -------------------------------------------------------------------------
    @discord.slash_command(
        name="play",
        description="Play a song — search by name or paste a YouTube/Spotify link",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def play(
        self,
        ctx: discord.ApplicationContext,
        query: Option(str, "Song name or YouTube/Spotify link"),
    ):
        channel = await self._require_music_access(ctx)
        if not channel:
            return

        if not _is_url_query(query):
            await ctx.defer(ephemeral=True)
            try:
                candidates = await self._search_candidates(query)
            except Exception as exc:
                logger.error("Search failed: %s", exc)
                return await ctx.followup.send(f"❌ Search failed: {exc}", ephemeral=True)

            if not candidates:
                return await ctx.followup.send("❌ No results — try different wording.", ephemeral=True)

            embed = discord.Embed(
                title="🔎 Pick a track",
                description=f"Results for **{query.strip()[:80]}**",
                color=THEME_PRIMARY,
            )
            view = SearchPickView(self, ctx.guild, channel, ctx.author, candidates)
            return await ctx.followup.send(embed=embed, view=view, ephemeral=True)

        self._cancel_leave_timer(self._get_player(ctx.guild.id))
        voice_task = asyncio.create_task(self._ensure_voice(ctx.guild, channel))
        await ctx.defer()

        try:
            tracks, _vc = await asyncio.gather(
                self._resolve_tracks(query, ctx.author.id, ctx.author.display_name),
                voice_task,
            )
            position = await self._enqueue(ctx.guild, channel, tracks)
        except Exception as exc:
            logger.error("Play failed: %s", exc)
            return await ctx.followup.send(f"❌ Could not play that: {exc}", ephemeral=True)

        embed, view = self._play_payload(ctx.guild.id, tracks, position)
        await ctx.followup.send(embed=embed, view=view)

    # -------------------------------------------------------------------------
    # /pause · /resume · /skip · /stop · /queue
    # -------------------------------------------------------------------------
    @discord.slash_command(
        name="pause",
        description="Pause the current song",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def pause(self, ctx: discord.ApplicationContext):
        if not has_music_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)
        vc = ctx.guild.voice_client
        if not vc or not vc.is_playing():
            return await ctx.respond("❌ Nothing is playing.", ephemeral=True)
        vc.pause()
        await ctx.respond("⏸️ Paused.", ephemeral=True)

    @discord.slash_command(
        name="resume",
        description="Resume playback",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def resume(self, ctx: discord.ApplicationContext):
        if not has_music_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)
        vc = ctx.guild.voice_client
        if not vc or not vc.is_paused():
            return await ctx.respond("❌ Nothing is paused.", ephemeral=True)
        vc.resume()
        await ctx.respond("▶️ Resumed.", ephemeral=True)

    @discord.slash_command(
        name="skip",
        description="Skip the current song",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def skip(self, ctx: discord.ApplicationContext):
        if not has_music_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)
        vc = ctx.guild.voice_client
        if not vc or not (vc.is_playing() or vc.is_paused()):
            return await ctx.respond("❌ Nothing is playing.", ephemeral=True)

        player = self._get_player(ctx.guild.id)
        skipped = player.current.title if player.current else "track"
        vc.stop()
        await ctx.respond(f"⏭️ Skipped **{skipped}**", ephemeral=True)

    @discord.slash_command(
        name="stop",
        description="Stop playback and clear the queue",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def stop(self, ctx: discord.ApplicationContext):
        if not has_music_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)
        player = self._get_player(ctx.guild.id)

        while not player.queue.empty():
            try:
                player.queue.get_nowait()
                player.queue.task_done()
            except asyncio.QueueEmpty:
                break

        player.current = None
        vc = ctx.guild.voice_client
        if vc:
            if vc.is_playing() or vc.is_paused():
                vc.stop()
            await vc.disconnect()

        if player.worker and not player.worker.done():
            player.worker.cancel()

        await ctx.respond("⏹️ Stopped — queue cleared, disconnected.", ephemeral=True)

    @discord.slash_command(
        name="queue",
        description="Show the music queue",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def queue_cmd(self, ctx: discord.ApplicationContext):
        if not has_music_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)
        embed = self._queue_embed(ctx.guild.id)
        if not embed:
            return await ctx.respond("📭 Queue is empty.", ephemeral=True)
        await ctx.respond(embed=embed, ephemeral=True)

    @discord.slash_command(
        name="nowplaying",
        description="Show the current song",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def nowplaying(self, ctx: discord.ApplicationContext):
        if not has_music_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)
        player = self._get_player(ctx.guild.id)
        if not player.current:
            return await ctx.respond("❌ Nothing is playing right now.", ephemeral=True)

        vc = ctx.guild.voice_client
        status = "⏸️ Paused" if vc and vc.is_paused() else "▶️ Live"
        embed = self._track_embed(player.current, title="🎵 Now Playing", status=status)
        await ctx.respond(embed=embed, view=MusicControlsView(self, ctx.guild.id))

    # -------------------------------------------------------------------------
    # Auto-play links pasted in chat
    # -------------------------------------------------------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        urls = _extract_urls(message.content)
        if not urls:
            return

        member = message.guild.get_member(message.author.id)
        if not member or not has_music_role(member):
            return
        if not getattr(member, "voice", None) or not member.voice.channel:
            try:
                await message.reply(
                    "🎵 Join a voice channel — I'll play that link when you're in.",
                    mention_author=False,
                    delete_after=20,
                )
            except Exception:
                pass
            return

        channel = member.voice.channel
        query = urls[0]

        try:
            tracks = await self._resolve_tracks(
                query, message.author.id, message.author.display_name
            )
            if not tracks:
                return
            position = await self._enqueue(message.guild, channel, tracks)
            embed, view = self._play_payload(message.guild.id, tracks, position)
            await message.reply(embed=embed, view=view, mention_author=False)
        except Exception as exc:
            logger.error("Auto-play from message failed: %s", exc)
            try:
                await message.reply("❌ Couldn't play that link.", mention_author=False, delete_after=10)
            except Exception:
                pass


def setup(bot: commands.Bot):
    bot.add_cog(MusicCog(bot))
