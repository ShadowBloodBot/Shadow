
# cogs/tts.py
import os
import asyncio
import html
import logging
import uuid
import shutil
from dataclasses import dataclass
from pathlib import Path

import aiohttp
import discord
from discord.ext import commands
from discord import Option, OptionChoice
import edge_tts

from cogs.guild_registry import REGISTERED_GUILD_IDS, ch_id, is_owner, resolve_channel, role_id

logger = logging.getLogger("ShadowSyn.TTS")

# --- CONSTANTS ---
THEME_PRIMARY       = 0x2B0B35
MAX_TEXT_LENGTH     = 250   # Protects against mega-spam timeouts
AUTO_LEAVE_TIMEOUT  = 120   # Leaves VC after 2 minutes of silence
VOICE_READY_TIMEOUT = 3.0   # Max wait for the voice link (incl. DAVE) before a clip plays anyway

TEMP_AUDIO_DIR = Path("temp_audio")
FFMPEG_BEFORE  = "-probesize 32 -analyzeduration 0"
FFMPEG_OPTIONS = "-loglevel error"

TRANSLATE_TIMEOUT = aiohttp.ClientTimeout(total=5)
TRANSLATE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
}

# --- LANGUAGE CONFIGURATION ---
TTS_LANGUAGES = [
    OptionChoice(name="English (US)",          value="en"),
    OptionChoice(name="English (Australian)",  value="au"),
    OptionChoice(name="English (UK)",          value="uk"),
    OptionChoice(name="Spanish",               value="es"),
    OptionChoice(name="French",                value="fr"),
    OptionChoice(name="German",                value="de"),
    OptionChoice(name="Italian",               value="it"),
    OptionChoice(name="Japanese",              value="ja"),
    OptionChoice(name="Korean",                value="ko"),
    OptionChoice(name="Russian",               value="ru"),
]

# English choices = accent only. All others = translate text, then speak in that language.
ENGLISH_ACCENTS = frozenset({"en", "au", "uk"})

TRANSLATE_TARGETS = {
    "es": "es",
    "fr": "fr",
    "de": "de",
    "it": "it",
    "ja": "ja",
    "ko": "ko",
    "ru": "ru",
}

# Edge TTS neural voices — one per /speak language choice
EDGE_VOICES = {
    "en": "en-US-JennyNeural",
    "au": "en-AU-NatashaNeural",
    "uk": "en-GB-SoniaNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "it": "it-IT-ElsaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "ru": "ru-RU-SvetlanaNeural",
}

def has_tts_role(user):
    if is_owner(user):
        return True
    if not isinstance(user, discord.Member):
        return False
    rid = role_id(user.guild.id, "member")
    if rid is None:
        return False
    return any(r.id == rid for r in user.roles)


# -----------------------------------------------------------------------------
# TRANSLATION — two free providers, tried in order
# -----------------------------------------------------------------------------
async def _translate_google(session: aiohttp.ClientSession, text: str, target: str) -> str:
    async with session.get(
        "https://translate.googleapis.com/translate_a/single",
        params={"client": "gtx", "sl": "auto", "tl": target, "dt": "t", "q": text},
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    return "".join(seg[0] for seg in data[0] if seg and seg[0])


async def _translate_mymemory(session: aiohttp.ClientSession, text: str, target: str) -> str:
    async with session.get(
        "https://api.mymemory.translated.net/get",
        params={"q": text, "langpair": f"en|{target}"},
    ) as resp:
        if resp.status != 200:
            raise RuntimeError(f"HTTP {resp.status}")
        data = await resp.json(content_type=None)
    # Quota exhaustion comes back as HTTP 200 with a 4xx responseStatus.
    if str(data.get("responseStatus")) != "200":
        raise RuntimeError(f"status {data.get('responseStatus')}")
    return html.unescape(data["responseData"]["translatedText"])


TRANSLATORS = (
    ("Google", _translate_google),
    ("MyMemory", _translate_mymemory),
)


async def translate_text(text: str, target: str) -> str:
    """Translate ``text`` to ``target``. Raises RuntimeError naming every provider failure."""
    failures = []
    async with aiohttp.ClientSession(timeout=TRANSLATE_TIMEOUT, headers=TRANSLATE_HEADERS) as session:
        for name, provider in TRANSLATORS:
            try:
                translated = (await provider(session, text, target) or "").strip()
            except Exception as exc:
                failures.append(f"{name}: {type(exc).__name__} {exc}".strip())
                continue
            if translated:
                return translated
            failures.append(f"{name}: empty result")
    raise RuntimeError("; ".join(failures))


class _SpeakFailure(Exception):
    """A /speak request that cannot be played: what to tell the user and what to log."""

    def __init__(self, user_msg: str, result: str, spoken_text: str | None = None):
        super().__init__(result)
        self.user_msg    = user_msg
        self.result      = result
        self.spoken_text = spoken_text


@dataclass
class _Clip:
    file_path: Path
    author: discord.Member
    voice_channel: discord.VoiceChannel
    original_text: str
    spoken_text: str
    is_translated: bool
    lang_name: str


class _GuildTTS:
    """Playback state for one guild. Main and Backup never share a queue."""

    def __init__(self):
        self.queue       = asyncio.Queue()  # pending _Clip items
        self.worker      = None             # asyncio.Task — sequential playback worker
        self.leave_timer = None             # asyncio.Task — AFK disconnect timer


class TTSCog(commands.Cog):
    def __init__(self, bot):
        self.bot     = bot
        self._guilds: dict[int, _GuildTTS] = {}
        self._startup_cleanup()

    def _state(self, guild_id: int) -> _GuildTTS:
        state = self._guilds.get(guild_id)
        if state is None:
            state = self._guilds[guild_id] = _GuildTTS()
        return state

    # -------------------------------------------------------------------------
    # 🧹 GARBAGE COLLECTOR: Wipes old temp files on boot
    # -------------------------------------------------------------------------
    def _startup_cleanup(self):
        if TEMP_AUDIO_DIR.exists():
            try:
                shutil.rmtree(TEMP_AUDIO_DIR)
                print("🧹 Cleared leftover TTS audio files.")
            except Exception as e:
                print(f"⚠️ Failed to clean temp dir: {e}")
        TEMP_AUDIO_DIR.mkdir(exist_ok=True)

    async def _ensure_voice(self, guild: discord.Guild, channel: discord.VoiceChannel):
        vc = guild.voice_client
        if not vc or not vc.is_connected():
            vc = await channel.connect(timeout=20.0)
        elif vc.channel.id != channel.id:
            await vc.move_to(channel)
        if not vc.is_connected():
            raise RuntimeError("Voice connection failed")
        return vc

    async def _wait_voice_ready(self, vc) -> tuple[float, str]:
        """Hold a clip until the voice link can carry it. Returns (seconds waited, DAVE state).

        py-cord reports "connected" before the DAVE (end-to-end encryption)
        handshake finishes, and sends frames without DAVE encryption until it
        does. A 2-3 second clip started in that window can be gone before
        anyone is able to hear it.
        """
        loop  = asyncio.get_running_loop()
        start = loop.time()
        while True:
            session = getattr(getattr(vc, "_connection", None), "dave_session", None)
            ready   = vc.is_connected() and (session is None or session.ready)
            waited  = loop.time() - start
            if ready or waited >= VOICE_READY_TIMEOUT:
                break
            await asyncio.sleep(0.05)
        if session is None:
            dave = "off"
        else:
            dave = "ready" if session.ready else "NOT ready"
        return waited, dave

    async def _post_speak_history(
        self,
        author: discord.Member,
        voice_channel: discord.VoiceChannel,
        original_text: str,
        spoken_text: str | None,
        is_translated: bool,
        lang_name: str,
        result: str,
    ):
        try:
            gid = author.guild.id if author.guild else None
            if gid is None:
                return
            thread = await resolve_channel(self.bot, gid, "tts_history")
            if thread is None:
                return

            embed = discord.Embed(
                title="🗣️ /speak Request",
                color=THEME_PRIMARY,
            )
            embed.add_field(name="User", value=f"{author.mention} (`{author.display_name}`)", inline=True)
            embed.add_field(name="Voice Channel", value=voice_channel.mention, inline=True)
            embed.add_field(name="Language", value=lang_name, inline=True)
            embed.add_field(name="English", value=original_text, inline=False)
            if is_translated and spoken_text:
                embed.add_field(name="Translation", value=spoken_text[:1024], inline=False)
            embed.add_field(name="Result", value=result[:1024], inline=False)
            embed.set_footer(text="ShadowSyn TTS History")

            await thread.send(embed=embed)
        except Exception as e:
            print(f"⚠️ TTS history log failed: {e}")

    # -------------------------------------------------------------------------
    # ⏳ AUTO-DISCONNECT: fires after queue empties and silence timeout elapses
    # -------------------------------------------------------------------------
    async def _schedule_leave(self, guild):
        await asyncio.sleep(AUTO_LEAVE_TIMEOUT)
        vc = guild.voice_client
        if vc and vc.is_connected() and not vc.is_playing():
            try:
                await vc.disconnect()
                print(f"👋 Auto-disconnected from {guild.name} due to inactivity.")
            except Exception as e:
                logger.warning("TTS: auto-disconnect failed in %s: %s", guild.id, e)

    def _arm_leave(self, guild: discord.Guild):
        """(Re)start the AFK timer, unless a worker is running — it arms its own on exit."""
        state = self._state(guild.id)
        if state.worker and not state.worker.done():
            return
        if state.leave_timer and not state.leave_timer.done():
            state.leave_timer.cancel()
        state.leave_timer = asyncio.create_task(self._schedule_leave(guild))

    def _music_is_active(self, guild_id: int) -> bool:
        music = self.bot.get_cog("MusicCog")
        return bool(music and music.is_active(guild_id))

    async def interrupt(self, guild: discord.Guild):
        """Music took over — stop TTS playback and clear the queue."""
        state = self._state(guild.id)
        if state.leave_timer and not state.leave_timer.done():
            state.leave_timer.cancel()
        state.leave_timer = None

        while not state.queue.empty():
            try:
                clip = state.queue.get_nowait()
                _safe_delete(clip.file_path)
            except asyncio.QueueEmpty:
                break

        vc = guild.voice_client
        if vc and vc.is_playing():
            vc.stop()

        if state.worker and not state.worker.done():
            state.worker.cancel()
            state.worker = None

    # -------------------------------------------------------------------------
    # 🎵 QUEUE WORKER: processes TTS clips one at a time, never overlapping
    # -------------------------------------------------------------------------
    async def _play_clip(self, guild: discord.Guild, clip: _Clip) -> str:
        """Play one clip to the end. Returns the outcome line for the history thread."""
        if self._music_is_active(guild.id):
            return "Not played — music took over"

        vc = guild.voice_client
        if not vc:
            return "Not played — voice connection dropped"
        waited, dave = await self._wait_voice_ready(vc)
        if not vc.is_connected():
            return "Not played — voice connection dropped"
        voice_note = f"voice ready after {waited:.1f}s · DAVE {dave}"

        # asyncio.Event lets us block here until the clip finishes
        done   = asyncio.Event()
        errors = []

        def after_play(error):
            # after_play fires from a thread — route back to the event loop safely
            if error:
                errors.append(error)
            self.bot.loop.call_soon_threadsafe(done.set)

        loop   = asyncio.get_running_loop()
        source = None
        try:
            source = discord.FFmpegOpusAudio(
                str(clip.file_path), before_options=FFMPEG_BEFORE, options=FFMPEG_OPTIONS
            )
            started = loop.time()
            vc.play(source, after=after_play)
        except Exception as exc:
            if source is not None:
                source.cleanup()
            logger.error(
                "TTS: playback failed to start in guild %s — %s: %s (%s)",
                guild.id, type(exc).__name__, exc, voice_note,
            )
            return f"Playback failed to start — {type(exc).__name__}: {exc} · {voice_note}"

        await done.wait()       # wait for clip to fully finish before next
        played = loop.time() - started
        if errors:
            exc = errors[0]
            logger.error(
                "TTS: playback error in guild %s after %.1fs — %s: %s (%s)",
                guild.id, played, type(exc).__name__, exc, voice_note,
            )
            return f"Playback error after {played:.1f}s — {type(exc).__name__}: {exc} · {voice_note}"
        logger.info("TTS: played %.1fs in guild %s (%s)", played, guild.id, voice_note)
        return f"Played {played:.1f}s · {voice_note}"

    async def _queue_worker(self, guild: discord.Guild):
        state = self._state(guild.id)
        try:
            while not state.queue.empty():
                clip = state.queue.get_nowait()
                try:
                    result = await self._play_clip(guild, clip)
                except Exception as exc:
                    # One bad clip must not kill the worker and strand the queue.
                    logger.exception("TTS: clip crashed in guild %s", guild.id)
                    result = f"Playback crashed — {type(exc).__name__}: {exc}"
                finally:
                    _safe_delete(clip.file_path)  # cleanup guaranteed — always runs here
                await self._post_speak_history(
                    clip.author,
                    clip.voice_channel,
                    clip.original_text,
                    clip.spoken_text,
                    clip.is_translated,
                    clip.lang_name,
                    result,
                )
        finally:
            # Worker finished — clear itself and start the AFK timer
            state.worker = None
            self._arm_leave(guild)

    # -------------------------------------------------------------------------
    # /speak
    # -------------------------------------------------------------------------
    @discord.slash_command(
        name="speak",
        description="Make the bot say something in your Voice Channel",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def speak(
        self,
        ctx,
        text:     Option(str, description=f"What do you want the bot to say? (Max {MAX_TEXT_LENGTH} chars)"),
        language: Option(str, description="English accent, or language (auto-translates your text)", choices=TTS_LANGUAGES, default="en")
    ):
        # --- GATE CHECKS (before defer = instant ephemeral errors, no spinner) ---
        if not has_tts_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)

        if len(text) > MAX_TEXT_LENGTH:
            return await ctx.respond(
                f"❌ Text too long — keep it under {MAX_TEXT_LENGTH} characters.", ephemeral=True
            )

        # 🚦 VC check BEFORE any API work — fail fast if not in a channel
        member = ctx.guild.get_member(ctx.author.id)
        if not getattr(member, "voice", None) or not member.voice.channel:
            return await ctx.respond("❌ You must be in a Voice Channel to use this.", ephemeral=True)

        if self._music_is_active(ctx.guild.id):
            return await ctx.respond(
                "❌ Music is playing — wait for the queue to finish or use `/stop` first.",
                ephemeral=True,
            )

        target_channel = member.voice.channel
        state = self._state(ctx.guild.id)

        if state.leave_timer:
            state.leave_timer.cancel()

        # Head-start voice handshake before defer — first /speak is connect-bound.
        voice_task = asyncio.create_task(self._ensure_voice(ctx.guild, target_channel))

        await ctx.defer(ephemeral=True)

        lang_name = next((c.name for c in TTS_LANGUAGES if c.value == language), language)
        file_path = TEMP_AUDIO_DIR / f"tts_{uuid.uuid4().hex[:8]}.mp3"

        async def prepare_audio():
            if language in ENGLISH_ACCENTS:
                spoken_text, is_translated = text, False
            else:
                try:
                    spoken_text = await translate_text(text, TRANSLATE_TARGETS[language])
                except Exception as exc:
                    raise _SpeakFailure(
                        f"❌ Couldn't translate to {lang_name} right now. Try again in a minute.",
                        f"Translation failed — {exc}",
                    ) from exc
                is_translated = spoken_text != text

            try:
                await edge_tts.Communicate(spoken_text, EDGE_VOICES[language]).save(str(file_path))
            except Exception as exc:
                raise _SpeakFailure(
                    "❌ Couldn't generate the speech audio. Try again.",
                    f"Speech synthesis failed — {type(exc).__name__}: {exc}",
                    spoken_text=spoken_text,
                ) from exc
            return spoken_text, is_translated

        prepared, vc = await asyncio.gather(prepare_audio(), voice_task, return_exceptions=True)

        failure = None
        if isinstance(prepared, _SpeakFailure):
            failure = prepared
        elif isinstance(prepared, BaseException):
            failure = _SpeakFailure(
                "❌ Audio setup failed. Try again.",
                f"Audio setup failed — {type(prepared).__name__}: {prepared}",
            )
        elif isinstance(vc, BaseException):
            failure = _SpeakFailure(
                "❌ Couldn't join your voice channel. Try again.",
                f"Voice connect failed — {type(vc).__name__}: {vc}",
                spoken_text=prepared[0],
            )
        elif not vc.is_connected():
            failure = _SpeakFailure(
                "❌ Connection lost before speaking.",
                "Not played — voice connection dropped before playback",
                spoken_text=prepared[0],
            )

        if failure is not None:
            _safe_delete(file_path)
            logger.warning("TTS: /speak failed in guild %s — %s", ctx.guild.id, failure.result)
            # The bot may have joined with nothing to say — do not leave it parked there.
            self._arm_leave(ctx.guild)
            await ctx.followup.send(failure.user_msg, ephemeral=True)
            await self._post_speak_history(
                ctx.author,
                target_channel,
                text,
                failure.spoken_text,
                bool(failure.spoken_text and failure.spoken_text != text),
                lang_name,
                failure.result,
            )
            return

        spoken_text, is_translated = prepared

        # --- ENQUEUE ---
        position = state.queue.qsize()   # 0 = plays next, 1 = second in line, etc.
        await state.queue.put(_Clip(
            file_path=file_path,
            author=ctx.author,
            voice_channel=target_channel,
            original_text=text,
            spoken_text=spoken_text,
            is_translated=is_translated,
            lang_name=lang_name,
        ))

        # Start a worker if one isn't already running
        if state.worker is None or state.worker.done():
            state.worker = asyncio.create_task(self._queue_worker(ctx.guild))

        # --- CONFIRMATION EMBED ---
        display_desc = f"🗣️ **Said:** {spoken_text}"
        if is_translated:
            display_desc += f"\n*(Translated from: {text})*"

        status = "▶️ Speaking now" if position == 0 else f"📋 Queued — position **#{position + 1}**"

        embed = discord.Embed(description=display_desc, color=THEME_PRIMARY)
        embed.set_footer(text=f"{status}  |  Requested by {ctx.author.display_name}  |  {lang_name}")
        await ctx.followup.send(embed=embed, ephemeral=True)


# -----------------------------------------------------------------------------
# HELPER
# -----------------------------------------------------------------------------
def _safe_delete(path: Path):
    try:
        if path.exists():
            os.remove(str(path))
    except Exception:
        pass


def setup(bot):
    bot.add_cog(TTSCog(bot))
