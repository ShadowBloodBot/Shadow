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
from googletrans import Translator

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
        self.translator = Translator()

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

        # 1. THE JTC CACHE FIX
        await asyncio.sleep(1.0)
        member = ctx.guild.get_member(ctx.author.id)

        if not getattr(member, "voice", None) or not member.voice.channel:
            return await ctx.followup.send("❌ You must be in a Voice Channel to use this.", ephemeral=True)
            
        target_channel = member.voice.channel

        # 2. TRANSLATION LOGIC
        lang_code = "en" if language in ["au", "uk"] else language
        tld = "com.au" if language == "au" else "co.uk" if language == "uk" else "com"
        
        spoken_text = text
        is_translated = False
        
        if lang_code != "en":
            try:
                # googletrans 4.0.0-rc1 uses async translation
                translation = await self.translator.translate(text, dest=lang_code)
                spoken_text = translation.text
                is_translated = True
            except Exception as e:
                print(f"⚠️ Translation Error: {e}")
                # If translation fails, it will fall back to reading English with an accent

        # 3. OFFLINE GENERATION
        file_name = f"tts_{uuid.uuid4().hex[:8]}.mp3"
        file_path = TEMP_AUDIO_DIR / file_name

        def generate_tts():
            tts = gTTS(text=spoken_text, lang=lang_code, tld=tld, slow=False)
            tts.save(str(file_path))

        try:
            await self.bot.loop.run_in_executor(None, generate_tts)
        except Exception as e:
            traceback.print_exc()
            return await ctx.followup.send(f"❌ Audio Generation Failed: {e}", ephemeral=True)

        # 4. PRE-LOAD AUDIO (Opus Engine)
        try:
            source = await discord.FFmpegOpusAudio.from_probe(str(file_path))
        except Exception as e:
            traceback.print_exc()
            return await ctx.followup.send(f"❌ Audio Encoding Failed: {e}", ephemeral=True)

        # 5. NATIVE CONNECTION
        vc = ctx.guild.voice_client
        try:
            if not vc or not vc.is_connected():
                vc = await target_channel.connect(timeout=20.0)
            elif vc.channel.id != target_channel.id:
                await vc.move_to(target_channel)
        except Exception as e:
            return await ctx.followup.send(f"❌ Voice Connection Failed: {e}", ephemeral=True)

        # 6. STABILIZATION BUFFER
        await asyncio.sleep(1.5)

        if not vc.is_connected():
            return await ctx.followup.send("❌ Connection lost before speaking.", ephemeral=True)

        if vc.is_playing():
            vc.stop() 

        # 7. STREAM & CLEANUP
        try:
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
            
            # Show what was actually translated in the UI
            display_desc = f"🗣️ **Said:** {spoken_text}"
            if is_translated:
                display_desc += f"\n*(Original: {text})*"
                
            embed = discord.Embed(description=display_desc, color=THEME_PRIMARY)
            embed.set_footer(text=f"Requested by {ctx.author.display_name} | {lang_name}")
            await ctx.followup.send(embed=embed)

        except Exception as e:
            traceback.print_exc()
            await ctx.followup.send(f"❌ Playback Execution Failed: {e}", ephemeral=True)

def setup(bot):
    bot.add_cog(TTSCog(bot))
