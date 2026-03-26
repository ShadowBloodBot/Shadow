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
            else: return await ctx.followup.send(*args, **kwargs)
    except: return None

async def ensure_voice(ctx):
    """Connects to the voice channel ONLY when explicitly called."""
    channel = ctx.author.voice.channel
    vc = ctx.guild.voice_client
    
    try:
        if vc:
            if vc.is_connected():
                if vc.channel.id != channel.id:
                    await vc.move_to(channel)
            else:
                # Clean up zombie connections before re-establishing
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
        
        # 3. Pre-flight Voice Check (Do not connect yet, just verify they are in a channel)
        if not isinstance(ctx.author, discord.Member) or not ctx.author.voice or not ctx.author.voice.channel:
            return await ctx.followup.send("❌ You must be in a Voice Channel to use this.", ephemeral=True)

        # 4. Collision Detection
        vc = ctx.guild.voice_client
        if vc and vc.is_playing():
            return await ctx.followup.send("⚠️ I am already speaking or playing music. Please wait.", ephemeral=True)

        try:
            # 5. Offline Generation Phase (Happens BEFORE joining the voice channel)
            file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
            file_path = TEMP_AUDIO_DIR / file_name

            def generate_tts():
                if language == "au":
                    tts = gTTS(text=text, lang="en", tld="com.au", slow=False)
                elif language == "uk":
                    tts = gTTS(text=text, lang="en", tld="co.uk", slow=False)
                else:
                    tts = gTTS(text=text, lang=language, slow=False)
                tts.save(str(file_path))

            await self.bot.loop.run_in_executor(None, generate_tts)

            # 6. Connection Phase (The file is ready, NOW we join)
            active_vc = await ensure_voice(ctx)
            if not active_vc: 
                return # Connection failed, error handled inside ensure_voice

            # 7. Execution Phase
            def after_play(error):
                if error: print(f"⚠️ TTS Playback Error: {error}")
                try:
                    if file_path.exists(): os.remove(str(file_path))
                except Exception as e:
                    print(f"⚠️ Failed to delete temp TTS file: {e}")

            source = discord.FFmpegPCMAudio(str(file_path), **FFMPEG_OPTIONS)
            active_vc.play(source, after=after_play)
            
            # Fetch human-readable language name for the log output
            lang_name = next((choice.name for choice in TTS_LANGUAGES if choice.value == language), language)
            
            embed = discord.Embed(description=f"🗣️ **Said:** {text}", color=THEME_PRIMARY)
            embed.set_footer(text=f"Requested by {ctx.author.display_name} | {lang_name}")
            await ctx.followup.send(embed=embed)

        except Exception as e:
            await ctx.followup.send(f"❌ Failed to generate speech: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(TTSCog(bot))
