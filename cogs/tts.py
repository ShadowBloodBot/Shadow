
# cogs/tts.py
import os
import asyncio
import uuid
import shutil
from pathlib import Path

import discord
from discord.ext import commands
from discord import Option, OptionChoice
import edge_tts
from deep_translator import GoogleTranslator

from cogs.guild_registry import REGISTERED_GUILD_IDS, ch_id, resolve_channel, role_id

# --- CONSTANTS ---
THEME_PRIMARY      = 0x2B0B35
MAX_TEXT_LENGTH    = 250   # Protects against mega-spam timeouts
AUTO_LEAVE_TIMEOUT = 120   # Leaves VC after 2 minutes of silence
VOICE_SETTLE_MAX   = 0.5   # Max wait after fresh connect (Railway); exits early when stable

TEMP_AUDIO_DIR = Path("temp_audio")
FFMPEG_BEFORE  = "-probesize 32 -analyzeduration 0"
FFMPEG_OPTIONS = "-loglevel error"

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
    if not isinstance(user, discord.Member):
        return False
    rid = role_id(user.guild.id, "member")
    if rid is None:
        return False
    return any(r.id == rid for r in user.roles)


class TTSCog(commands.Cog):
    def __init__(self, bot):
        self.bot          = bot
        self.leave_timer  = None         # asyncio.Task — AFK disconnect timer
        self.queue        = asyncio.Queue()  # pending TTS items
        self.queue_worker = None         # asyncio.Task — sequential playback worker
        self._startup_cleanup()

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

    async def _post_speak_history(
        self,
        author: discord.Member,
        voice_channel: discord.VoiceChannel,
        original_text: str,
        spoken_text: str,
        is_translated: bool,
        lang_name: str,
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
            if is_translated:
                embed.add_field(name="Translation", value=spoken_text, inline=False)
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
            await vc.disconnect()
            print(f"👋 Auto-disconnected from {guild.name} due to inactivity.")

    def _music_is_active(self, guild_id: int) -> bool:
        music = self.bot.get_cog("MusicCog")
        return bool(music and music.is_active(guild_id))

    async def interrupt(self, guild: discord.Guild):
        """Music took over — stop TTS playback and clear the queue."""
        if self.leave_timer and not self.leave_timer.done():
            self.leave_timer.cancel()
        self.leave_timer = None

        while not self.queue.empty():
            try:
                _source, file_path = self.queue.get_nowait()
                _safe_delete(file_path)
            except asyncio.QueueEmpty:
                break

        vc = guild.voice_client
        if vc and vc.is_playing():
            vc.stop()

        if self.queue_worker and not self.queue_worker.done():
            self.queue_worker.cancel()
            self.queue_worker = None

    # -------------------------------------------------------------------------
    # 🎵 QUEUE WORKER: processes TTS clips one at a time, never overlapping
    # -------------------------------------------------------------------------
    async def _queue_worker(self, guild: discord.Guild):
        try:
            while not self.queue.empty():
                source, file_path = await self.queue.get()

                if self._music_is_active(guild.id):
                    _safe_delete(file_path)
                    continue

                vc = guild.voice_client
                if not vc or not vc.is_connected():
                    _safe_delete(file_path)
                    continue

                # asyncio.Event lets us block here until the clip finishes
                done = asyncio.Event()

                def after_play(error):
                    # after_play fires from a thread — route back to the event loop safely
                    self.bot.loop.call_soon_threadsafe(done.set)

                vc.play(source, after=after_play)
                await done.wait()       # wait for clip to fully finish before next
                _safe_delete(file_path) # cleanup guaranteed — always runs here

        finally:
            # Worker finished — clear itself and start the AFK timer
            self.queue_worker = None
            self.leave_timer  = asyncio.create_task(self._schedule_leave(guild))

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

        if self.leave_timer:
            self.leave_timer.cancel()

        # Head-start voice handshake before defer — first /speak is connect-bound.
        voice_task = asyncio.create_task(self._ensure_voice(ctx.guild, target_channel))

        await ctx.defer(ephemeral=True)

        lang_name = next((c.name for c in TTS_LANGUAGES if c.value == language), language)
        file_path = TEMP_AUDIO_DIR / f"tts_{uuid.uuid4().hex[:8]}.mp3"

        async def prepare_audio():
            if language in ENGLISH_ACCENTS:
                spoken_text, is_translated = text, False
            else:
                target = TRANSLATE_TARGETS[language]

                def translate():
                    translated = GoogleTranslator(source="auto", target=target).translate(text)
                    if not translated or not translated.strip():
                        raise RuntimeError("Translation returned empty result")
                    return translated.strip()

                try:
                    spoken_text = await self.bot.loop.run_in_executor(None, translate)
                except Exception as exc:
                    raise RuntimeError(f"Could not translate to {lang_name}") from exc
                is_translated = spoken_text != text

            await edge_tts.Communicate(spoken_text, EDGE_VOICES[language]).save(str(file_path))
            return spoken_text, is_translated

        try:
            (spoken_text, is_translated), vc = await asyncio.gather(
                prepare_audio(),
                voice_task,
            )
            if not vc.is_connected():
                _safe_delete(file_path)
                return await ctx.followup.send("❌ Connection lost before speaking.", ephemeral=True)
            source = discord.FFmpegOpusAudio(
                str(file_path), before_options=FFMPEG_BEFORE, options=FFMPEG_OPTIONS
            )
        except Exception as e:
            _safe_delete(file_path)
            return await ctx.followup.send(f"❌ Audio/voice setup failed: {e}", ephemeral=True)

        # --- ENQUEUE ---
        position = self.queue.qsize()   # 0 = plays next, 1 = second in line, etc.
        await self.queue.put((source, file_path))

        # Start a worker if one isn't already running
        if self.queue_worker is None or self.queue_worker.done():
            self.queue_worker = asyncio.create_task(self._queue_worker(ctx.guild))

        # --- CONFIRMATION EMBED ---
        display_desc = f"🗣️ **Said:** {spoken_text}"
        if is_translated:
            display_desc += f"\n*(Translated from: {text})*"

        status = "▶️ Speaking now" if position == 0 else f"📋 Queued — position **#{position + 1}**"

        embed = discord.Embed(description=display_desc, color=THEME_PRIMARY)
        embed.set_footer(text=f"{status}  |  Requested by {ctx.author.display_name}  |  {lang_name}")
        await ctx.followup.send(embed=embed, ephemeral=True)

        await self._post_speak_history(
            ctx.author,
            target_channel,
            text,
            spoken_text,
            is_translated,
            lang_name,
        )


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
