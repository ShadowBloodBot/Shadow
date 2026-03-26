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
FFMPEG_OPTIONS = {'options': '-vn'}
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

# --- HELPERS ---
def has_tts_role(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == TTS_ROLE_ID for r in user.roles)

async def indestructible_voice(ctx):
    """Nukes Discord API ghost states before connecting."""
    channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client

    # 1. If perfectly healthy, keep it.
    if vc and vc.is_connected() and vc.channel.id == channel.id:
        return vc

    # 2. Force terminate local dead socket
    if vc:
        try: await vc.disconnect(force=True)
        except: pass

    # 3. GHOST BUSTER: Nuke the server-side voice state to unstick the API
    try: await ctx.guild.change_voice_state(channel=None)
    except: pass
    await asyncio.sleep(1.5) # Allow Discord backend to flush

    # 4. Fresh Connection
    try:
        vc = await channel.connect(timeout=15, reconnect=False)
        return vc
    except Exception as e:
        print(f"CRITICAL VOICE ERROR: {e}")
        return None

# --- COG LOGIC ---
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
            return await ctx.respond("⛔ Restricted. You do not have the required role to use TTS.", ephemeral=True)

        await ctx.defer() 
        
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.followup.send("❌ You must be in a Voice Channel to use this.", ephemeral=True)

        vc = ctx.guild.voice_client
        if vc and vc.is_playing():
            return await ctx.followup.send("⚠️ I am already speaking or playing music. Please wait.", ephemeral=True)

        try:
            # 1. Offline Generation
            file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
            file_path = TEMP_AUDIO_DIR / file_name

            def generate_tts():
                if language == "au": tts = gTTS(text=text, lang="en", tld="com.au", slow=False)
                elif language == "uk": tts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
                else: tts = gTTS(text=text, lang=language, slow=False)
                tts.save(str(file_path))

            await self.bot.loop.run_in_executor(None, generate_tts)

            # 2. Secure Voice Connection
            active_vc = await indestructible_voice(ctx)
            if not active_vc or not active_vc.is_connected(): 
                return await ctx.followup.send("❌ Discord's Voice Gateway refused the connection. The server is stuck in a ghost state. Kick the bot manually and try again.", ephemeral=True)

            # 3. Stream & Delayed Cleanup
            source = discord.FFmpegPCMAudio(str(file_path), **FFMPEG_OPTIONS)
            
            def after_play(error):
                if error: print(f"⚠️ TTS Playback Error: {error}")
                async def cleanup():
                    await asyncio.sleep(2.0) # Prevent FFmpeg file lock crashes
                    try:
                        if file_path.exists(): os.remove(str(file_path))
                    except Exception as e: print(f"⚠️ Cleanup failed: {e}")
                asyncio.run_coroutine_threadsafe(cleanup(), self.bot.loop)

            active_vc.play(source, after=after_play)
            
            lang_name = next((choice.name for choice in TTS_LANGUAGES if choice.value == language), language)
            embed = discord.Embed(description=f"🗣️ **Said:** {text}", color=THEME_PRIMARY)
            embed.set_footer(text=f"Requested by {ctx.author.display_name} | {lang_name}")
            await ctx.followup.send(embed=embed)

        except Exception as e:
            traceback.print_exc()
            await ctx.followup.send(f"❌ Failed to generate speech: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(TTSCog(bot))
