# cogs/tts.py
import os
import asyncio
import uuid
import traceback
import shutil
from pathlib import Path

import discord
from discord.ext import commands
from discord import Option, OptionChoice
from gtts import gTTS
from deep_translator import GoogleTranslator

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
TTS_ROLE_ID = 955600320287887400
MAX_TEXT_LENGTH = 250 # Protects against mega-spam timeouts
AUTO_LEAVE_TIMEOUT = 120 # Leaves VC after 2 minutes of silence

TEMP_AUDIO_DIR = Path("temp_audio")

# --- LANGUAGE CONFIGURATION ---
TTS_LANGUAGES = [
    OptionChoice(name="English (US)", value="en"),
    OptionChoice(name="English (Australian)", value="au"),
    OptionChoice(name="English (UK)", value="uk"),
    OptionChoice(name="Spanish", value="es"),
    OptionChoice(name="French", value="fr"),
    OptionChoice(name="German", value="de"),
    OptionChoice(name="Italian", value="it"),
    OptionChoice(name="Japanese", value="ja"),
    OptionChoice(name="Korean", value="ko"),
    OptionChoice(name="Russian", value="ru"),
]

def has_tts_role(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == TTS_ROLE_ID for r in user.roles)

class TTSCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.leave_timers = {} # Tracks AFK timers for different servers
        self._startup_cleanup()

    # 🧹 1. GARBAGE COLLECTOR: Wipes old files on boot
    def _startup_cleanup(self):
        if TEMP_AUDIO_DIR.exists():
            try:
                shutil.rmtree(TEMP_AUDIO_DIR)
                print("🧹 Cleared leftover TTS audio files.")
            except Exception as e:
                print(f"⚠️ Failed to clean temp dir: {e}")
        TEMP_AUDIO_DIR.mkdir(exist_ok=True)

    # ⏳ 2. AUTO-DISCONNECT LOGIC
    async def schedule_leave(self, guild):
        await asyncio.sleep(AUTO_LEAVE_TIMEOUT)
        if guild.voice_client and guild.voice_client.is_connected() and not guild.voice_client.is_playing():
            await guild.voice_client.disconnect()
            print(f"👋 Auto-disconnected from {guild.name} due to inactivity.")

    @discord.slash_command(name="speak", description="Make the bot say something in your Voice Channel")
    async def speak(
        self, 
        ctx, 
        text: Option(str, description=f"What do you want the bot to say? (Max {MAX_TEXT_LENGTH} chars)"), 
        language: Option(str, description="Select the language or accent", choices=TTS_LANGUAGES, default="en")
    ):
        if not has_tts_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)

        # 🚦 3. SPAM PROTECTION
        if len(text) > MAX_TEXT_LENGTH:
            return await ctx.respond(f"❌ Text is too long! Keep it under {MAX_TEXT_LENGTH} characters.", ephemeral=True)

        await ctx.defer(ephemeral=True) 

        # Cancel any pending AFK leave timer for this server
        if ctx.guild.id in self.leave_timers:
            self.leave_timers[ctx.guild.id].cancel()

        lang_code = "en" if language in ["au", "uk"] else language
        tld = "com.au" if language == "au" else "co.uk" if language == "uk" else "com"

        def fetch_translation():
            if lang_code == "en": return text, False
            try:
                target = "zh-CN" if lang_code == "zh-cn" else lang_code
                result = GoogleTranslator(source='auto', target=target).translate(text)
                return result, True
            except Exception:
                return text, False

        translation_task = self.bot.loop.run_in_executor(None, fetch_translation)

        await asyncio.sleep(1.0)
        member = ctx.guild.get_member(ctx.author.id)

        if not getattr(member, "voice", None) or not member.voice.channel:
            return await ctx.followup.send("❌ You must be in a Voice Channel to use this.", ephemeral=True)
            
        target_channel = member.voice.channel
        spoken_text, is_translated = await translation_task

        file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        file_path = TEMP_AUDIO_DIR / file_name

        def generate_tts():
            tts = gTTS(text=spoken_text, lang=lang_code, tld=tld, slow=False)
            tts.save(str(file_path))

        try:
            await self.bot.loop.run_in_executor(None, generate_tts)
            source = await discord.FFmpegOpusAudio.from_probe(str(file_path), options='-loglevel error')
        except Exception as e:
            return await ctx.followup.send(f"❌ Audio Processing Failed: {e}", ephemeral=True)

        vc = ctx.guild.voice_client
        try:
            if not vc or not vc.is_connected():
                vc = await target_channel.connect(timeout=20.0)
            elif vc.channel.id != target_channel.id:
                await vc.move_to(target_channel)
        except Exception as e:
            return await ctx.followup.send(f"❌ Voice Connection Failed: {e}", ephemeral=True)

        await asyncio.sleep(1.5)

        if not vc.is_connected():
            return await ctx.followup.send("❌ Connection lost before speaking.", ephemeral=True)

        # 🔀 4. INTERRUPT HANDLING
        if vc.is_playing():
            vc.stop() 

        try:
            def after_play(error):
                # Start the AFK timer when audio finishes
                self.leave_timers[ctx.guild.id] = self.bot.loop.create_task(self.schedule_leave(ctx.guild))
                
                # Normal file cleanup
                async def cleanup():
                    await asyncio.sleep(2.0)
                    try:
                        if file_path.exists(): os.remove(str(file_path))
                    except: pass
                asyncio.run_coroutine_threadsafe(cleanup(), self.bot.loop)

            vc.play(source, after=after_play)
            
            lang_name = next((choice.name for choice in TTS_LANGUAGES if choice.value == language), language)
            
            display_desc = f"🗣️ **Said:** {spoken_text}"
            if is_translated:
                display_desc += f"\n*(Original: {text})*"
                
            embed = discord.Embed(description=display_desc, color=THEME_PRIMARY)
            embed.set_footer(text=f"Requested by {ctx.author.display_name} | {lang_name}")
            await ctx.followup.send(embed=embed, ephemeral=True)

        except Exception as e:
            await ctx.followup.send(f"❌ Playback Failed: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(TTSCog(bot))
