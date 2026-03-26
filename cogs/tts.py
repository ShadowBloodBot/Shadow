# cogs/tts.py
import os
import asyncio
import uuid
import traceback
from pathlib import Path

import discord
from discord.ext import commands
from discord import Option, OptionChoice
from gtts import gTTS

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
TTS_ROLE_ID = 955600320287887400

TEMP_AUDIO_DIR = Path("temp_audio")
TEMP_AUDIO_DIR.mkdir(exist_ok=True)

# --- LANGUAGE CONFIGURATION ---
TTS_LANGUAGES = [
    OptionChoice(name="English (US)", value="en"),
    OptionChoice(name="English (Australian)", value="au"),
    OptionChoice(name="English (UK)", value="uk"),
    OptionChoice(name="Spanish", value="es"),
    OptionChoice(name="French", value="fr"),
    OptionChoice(name="German", value="de"),
    OptionChoice(name="Italian", value="it"),
    OptionChoice(name="Portuguese", value="pt"),
    OptionChoice(name="Japanese", value="ja"),
    OptionChoice(name="Korean", value="ko"),
    OptionChoice(name="Chinese (Mandarin)", value="zh-cn"),
    OptionChoice(name="Russian", value="ru"),
    OptionChoice(name="Arabic", value="ar"),
    OptionChoice(name="Hindi", value="hi"),
    OptionChoice(name="Turkish", value="tr"),
    OptionChoice(name="Dutch", value="nl"),
    OptionChoice(name="Polish", value="pl"),
    OptionChoice(name="Swedish", value="sv"),
    OptionChoice(name="Indonesian", value="id"),
    OptionChoice(name="Vietnamese", value="vi")
]

def has_tts_role(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == TTS_ROLE_ID for r in user.roles)

class TTSCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @discord.slash_command(name="speak", description="Make the bot say something in your Voice Channel")
    async def speak(
        self, 
        ctx, 
        text: Option(str, description="What do you want the bot to say?"), 
        language: Option(str, description="Select the language or accent", choices=TTS_LANGUAGES, default="en")
    ):
        if not has_tts_role(ctx.author):
            return await ctx.respond("⛔ Restricted.", ephemeral=True)

        await ctx.defer() 
        
        if not getattr(ctx.author, "voice", None) or not ctx.author.voice.channel:
            return await ctx.followup.send("❌ You must be in a Voice Channel to use this.", ephemeral=True)

        # 1. OFFLINE GENERATION
        file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        file_path = TEMP_AUDIO_DIR / file_name

        def generate_tts():
            tld = "com.au" if language == "au" else "co.uk" if language == "uk" else "com"
            lang_code = "en" if language in ["au", "uk"] else language
            tts = gTTS(text=text, lang=lang_code, tld=tld, slow=False)
            tts.save(str(file_path))

        try:
            await self.bot.loop.run_in_executor(None, generate_tts)
        except Exception as e:
            traceback.print_exc()
            return await ctx.followup.send(f"❌ Audio Generation Failed: {e}", ephemeral=True)

        # 2. CLEAN NATIVE CONNECTION
        vc = ctx.guild.voice_client
        try:
            if not vc or not vc.is_connected():
                vc = await ctx.author.voice.channel.connect(timeout=20.0)
            elif vc.channel.id != ctx.author.voice.channel.id:
                await vc.move_to(ctx.author.voice.channel)
        except Exception as e:
            return await ctx.followup.send(f"❌ Voice Connection Failed: {e}", ephemeral=True)

        if vc.is_playing():
            return await ctx.followup.send("⚠️ I am already speaking. Please wait.", ephemeral=True)

        # 3. THE EXPERT FIX: FFmpegOpusAudio
        # This bypasses the Python GIL and encrypts natively, stopping Py-cord from crashing.
        try:
            source = await discord.FFmpegOpusAudio.from_probe(str(file_path))
            
            def after_play(error):
                if error: print(f"⚠️ TTS Playback Error: {error}")
                async def cleanup():
                    await asyncio.sleep(2.0)
                    try:
                        if file_path.exists(): os.remove(str(file_path))
                    except: pass
                asyncio.run_coroutine_threadsafe(cleanup(), self.bot.loop)

            vc.play(source, after=after_play)
            
            lang_name = next((choice.name for choice in TTS_LANGUAGES if choice.value == language), language)
            embed = discord.Embed(description=f"🗣️ **Said:** {text}", color=THEME_PRIMARY)
            embed.set_footer(text=f"Requested by {ctx.author.display_name} | {lang_name}")
            await ctx.followup.send(embed=embed)

        except Exception as e:
            traceback.print_exc()
            await ctx.followup.send(f"❌ Playback Execution Failed: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(TTSCog(bot))
