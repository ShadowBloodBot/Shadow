# cogs/tts.py
import os
import asyncio
import uuid
from pathlib import Path

import discord
from discord.ext import commands
from discord import Option, OptionChoice
from gtts import gTTS

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
FFMPEG_OPTIONS = {'options': '-vn'}
TTS_ROLE_ID = 955600320287887400

# Ensure a temp directory exists for the audio files
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

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

async def ensure_voice(ctx):
    if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
        await safe_reply(ctx, "❌ You must be in a Voice Channel to use this.", ephemeral=True)
        return None
    
    channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client
    
    try:
        if vc:
            if vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
            else:
                # Armored: Force cleanup of dead UDP sockets before reconnecting
                try: await vc.disconnect(force=True)
                except: pass
                vc = await channel.connect(timeout=20, reconnect=True)
        else:
            vc = await channel.connect(timeout=20, reconnect=True)
        return vc
    except Exception as e:
        await safe_reply(ctx, f"❌ Voice Error: {e}", ephemeral=True)
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
        # 1. Security Check
        if not has_tts_role(ctx.author):
            return await safe_reply(ctx, "⛔ Restricted. You do not have the required role to use TTS.", ephemeral=True)

        # 2. Armored Deferral
        await ctx.defer() 
        
        vc = await ensure_voice(ctx)
        if not vc: return
        
        # 3. Collision Detection
        if vc.is_playing():
            return await ctx.followup.send("⚠️ I am already speaking or playing music. Please wait.", ephemeral=True)

        try:
            file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
            file_path = TEMP_AUDIO_DIR / file_name

            # Offload blocking network call to prevent event loop stutter
            def generate_tts():
                # Handle specific top-level domains for regional accents
                if language == "au":
                    tts = gTTS(text=text, lang="en", tld="com.au", slow=False)
                elif language == "uk":
                    tts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
                else:
                    tts = gTTS(text=text, lang=language, slow=False)
                
                tts.save(str(file_path))

            await self.bot.loop.run_in_executor(None, generate_tts)

            # Define automatic cleanup to protect container storage
            def after_play(error):
                if error: print(f"⚠️ TTS Playback Error: {error}")
                try:
                    if file_path.exists(): os.remove(str(file_path))
                except Exception as e:
                    print(f"⚠️ Failed to delete temp TTS file: {e}")

            # 4. ARMOR CHECK: Did Discord drop us while downloading the audio?
            if not vc.is_connected():
                try: await vc.disconnect(force=True)
                except: pass
                vc = await ctx.author.voice.channel.connect(timeout=20, reconnect=True)

            # 5. Stream Execution
            source = discord.FFmpegPCMAudio(str(file_path), **FFMPEG_OPTIONS)
            vc.play(source, after=after_play)
            
            # Fetch human-readable language name for the log output
            lang_name = next((choice.name for choice in TTS_LANGUAGES if choice.value == language), language)
            
            embed = discord.Embed(description=f"🗣️ **Said:** {text}", color=THEME_PRIMARY)
            embed.set_footer(text=f"Requested by {ctx.author.display_name} | {lang_name}")
            await ctx.followup.send(embed=embed)

        except Exception as e:
            await ctx.followup.send(f"❌ Failed to generate speech: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(TTSCog(bot))
