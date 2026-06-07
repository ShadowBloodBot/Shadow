
# cogs/tts.py
import os
import asyncio
import uuid
import shutil
from pathlib import Path

import discord
from discord.ext import commands
from discord import Option, OptionChoice
from gtts import gTTS
from deep_translator import GoogleTranslator

# --- CONSTANTS ---
THEME_PRIMARY      = 0x2B0B35
TTS_ROLE_ID        = 955600320287887400
MAX_TEXT_LENGTH    = 250   # Protects against mega-spam timeouts
AUTO_LEAVE_TIMEOUT = 120   # Leaves VC after 2 minutes of silence

TEMP_AUDIO_DIR = Path("temp_audio")

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

def has_tts_role(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == TTS_ROLE_ID for r in user.roles)


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

    # -------------------------------------------------------------------------
    # ⏳ AUTO-DISCONNECT: fires after queue empties and silence timeout elapses
    # -------------------------------------------------------------------------
    async def _schedule_leave(self, guild):
        await asyncio.sleep(AUTO_LEAVE_TIMEOUT)
        vc = guild.voice_client
        if vc and vc.is_connected() and not vc.is_playing():
            await vc.disconnect()
            print(f"👋 Auto-disconnected from {guild.name} due to inactivity.")

    # -------------------------------------------------------------------------
    # 🎵 QUEUE WORKER: processes TTS clips one at a time, never overlapping
    # -------------------------------------------------------------------------
    async def _queue_worker(self, guild: discord.Guild):
        try:
            while not self.queue.empty():
                source, file_path = await self.queue.get()

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
    @discord.slash_command(name="speak", description="Make the bot say something in your Voice Channel")
    async def speak(
        self,
        ctx,
        text:     Option(str, description=f"What do you want the bot to say? (Max {MAX_TEXT_LENGTH} chars)"),
        language: Option(str, description="Select the language or accent", choices=TTS_LANGUAGES, default="en")
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

        target_channel = member.voice.channel

        await ctx.defer(ephemeral=True)

        # Cancel any pending AFK leave timer — we're about to speak again
        if self.leave_timer:
            self.leave_timer.cancel()

        # --- TRANSLATION (executor — blocking HTTP call) ---
        lang_code = "en" if language in ("au", "uk") else language
        tld       = "com.au" if language == "au" else "co.uk" if language == "uk" else "com"

        def fetch_translation():
            if lang_code == "en":
                return text, False
            try:
                target = "zh-CN" if lang_code == "zh-cn" else lang_code
                result = GoogleTranslator(source="auto", target=target).translate(text)
                return result, True
            except Exception:
                return text, False

        spoken_text, is_translated = await self.bot.loop.run_in_executor(None, fetch_translation)

        # --- TTS GENERATION (executor — gTTS makes a blocking HTTP call) ---
        file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        file_path = TEMP_AUDIO_DIR / file_name

        def generate_tts():
            gTTS(text=spoken_text, lang=lang_code, tld=tld, slow=False).save(str(file_path))

        try:
            await self.bot.loop.run_in_executor(None, generate_tts)
            source = await discord.FFmpegOpusAudio.from_probe(str(file_path), options="-loglevel error")
        except Exception as e:
            _safe_delete(file_path)  # cleanup even on generation failure
            return await ctx.followup.send(f"❌ Audio generation failed: {e}", ephemeral=True)

        # --- VOICE CONNECTION ---
        vc = ctx.guild.voice_client
        try:
            if not vc or not vc.is_connected():
                vc = await target_channel.connect(timeout=20.0)
                await asyncio.sleep(1.5)  # Railway voice gateway stabilisation
            elif vc.channel.id != target_channel.id:
                await vc.move_to(target_channel)
        except Exception as e:
            _safe_delete(file_path)
            return await ctx.followup.send(f"❌ Voice connection failed: {e}", ephemeral=True)

        if not vc.is_connected():
            _safe_delete(file_path)
            return await ctx.followup.send("❌ Connection lost before speaking.", ephemeral=True)

        # --- ENQUEUE ---
        position = self.queue.qsize()   # 0 = plays next, 1 = second in line, etc.
        await self.queue.put((source, file_path))

        # Start a worker if one isn't already running
        if self.queue_worker is None or self.queue_worker.done():
            self.queue_worker = asyncio.create_task(self._queue_worker(ctx.guild))

        # --- CONFIRMATION EMBED ---
        lang_name    = next((c.name for c in TTS_LANGUAGES if c.value == language), language)
        display_desc = f"🗣️ **Said:** {spoken_text}"
        if is_translated:
            display_desc += f"\n*(Original: {text})*"

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
