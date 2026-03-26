# cogs/music.py
import asyncio
from collections import deque
import discord
from discord import Option, SelectOption, Interaction
from discord.ui import View, Select
from discord.ext import commands
import yt_dlp

# --- CONSTANTS ---
ROLE_ADMIN_ID = 1214794734770323466 
ROLE_DJ_ID = 955600320287887400

# --- HELPERS ---
def dj_or_admin():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member): return False
        if any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles): return True
        if any(r.id == ROLE_DJ_ID for r in ctx.author.roles): return True
        return False
    return commands.check(predicate)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

async def ensure_voice_simple(ctx):
    """Safely connects to VC without triggering Py-cord's fatal _MissingSentinel crash."""
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    if not user.voice or not user.voice.channel:
        await safe_reply(ctx, "❌ Join a VC first!", ephemeral=True)
        return None
        
    channel = user.voice.channel
    vc = ctx.guild.voice_client
    
    try:
        if vc:
            if not vc.is_connected():
                # STANDARD disconnect. Never use force=True in Py-cord here.
                try: await vc.disconnect() 
                except: pass
                vc = await channel.connect(timeout=20, reconnect=True)
                await asyncio.sleep(0.5) # UDP Stabilization Buffer
            elif vc.channel.id != channel.id:
                await vc.move_to(channel)
                await asyncio.sleep(0.5)
        else: 
            vc = await channel.connect(timeout=20, reconnect=True)
            await asyncio.sleep(0.5)
        return vc
    except Exception as e: 
        print(f"Music Connect Error: {e}")
        await safe_reply(ctx, f"❌ Voice Error: {e}", ephemeral=True)
        return None

# --- MUSIC LOGIC ---

# Heavy options for actual playback
YTDL_PLAY_OPTIONS = {
    'format': 'bestaudio/best', 
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', 
    'restrictfilenames': True, 
    'noplaylist': True, 
    'nocheckcertificate': True, 
    'ignoreerrors': False, 
    'logtostderr': False, 
    'quiet': True, 
    'no_warnings': True, 
    'default_search': 'auto', 
    'source_address': '0.0.0.0', 
    'socket_timeout': 15, 
    'retries': 5
}

# Ultra-lightweight options purely for fetching track titles fast
YTDL_SEARCH_OPTIONS = {
    'format': 'bestaudio/best',
    'extract_flat': True,
    'skip_download': True,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0'
}

# Aggressive anti-stutter buffering for Railway
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn -b:a 128k -bufsize 64k'
}

ytdl_play = yt_dlp.YoutubeDL(YTDL_PLAY_OPTIONS)

class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data; self.title = data.get('title'); self.url = data.get('url')
        
    @classmethod
    async def from_url(cls, url, *, loop=None, stream=True):
        loop = loop or asyncio.get_running_loop()
        data = await loop.run_in_executor(None, lambda: ytdl_play.extract_info(url, download=not stream))
        if 'entries' in data: data = data['entries'][0]
        filename = data['url'] if stream else ytdl_play.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **FFMPEG_OPTIONS), data=data)

def check_queue(bot, gid, vc):
    if gid in bot.audio_queues and bot.audio_queues[gid]:
        url, title = bot.audio_queues[gid].popleft()
        asyncio.run_coroutine_threadsafe(play_track(bot, vc, url, title, gid), bot.loop)

async def play_track(bot, vc, url, title, gid):
    try:
        player = await YTDLSource.from_url(url, loop=bot.loop, stream=True)
        vc.play(player, after=lambda e: check_queue(bot, gid, vc))
    except Exception as e: 
        print(f"[Music] Playback Error: {e}")

class MusicSelect(Select):
    def __init__(self, entries, ctx, vc, bot):
        self.ctx = ctx; self.vc = vc; self.entries = entries; self.bot = bot
        options = [SelectOption(label=f"{i+1}. {e.get('title', 'Unknown')[:90]}", value=str(i)) for i, e in enumerate(entries[:5])]
        super().__init__(placeholder="Select a track...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id: 
            return await interaction.response.send_message("❌ Not your request.", ephemeral=True)
            
        await interaction.response.defer()
        
        # Remove the dropdown immediately so it can't be clicked twice
        try: await interaction.message.edit(view=None)
        except: pass
        
        selected = self.entries[int(self.values[0])]
        url = selected.get('url') or selected.get('webpage_url')
        title = selected.get('title')
        
        if not url: return await interaction.followup.send("❌ Error: Could not resolve URL.")

        if self.vc.is_playing():
            if self.ctx.guild.id not in self.bot.audio_queues: self.bot.audio_queues[self.ctx.guild.id] = deque()
            self.bot.audio_queues[self.ctx.guild.id].append((url, title))
            await interaction.followup.send(f"📝 **Queued:** {title}")
        else:
            await interaction.followup.send(f"▶️ **Playing:** {title}")
            await play_track(self.bot, self.vc, url, title, self.ctx.guild.id)

class MusicSelectionView(View):
    def __init__(self, entries, ctx, vc, bot):
        super().__init__(timeout=60)
        self.add_item(MusicSelect(entries, ctx, vc, bot))

class MusicCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, 'audio_queues'): self.bot.audio_queues = {}

    @discord.slash_command(name="play", description="Play a song")
    @dj_or_admin()
    async def play(self, ctx, search: str):
        if hasattr(ctx, 'defer'): await ctx.defer()
        
        vc = await ensure_voice_simple(ctx)
        if not vc: return
        
        # Now uses the ultra-lightweight YTDL_SEARCH_OPTIONS
        info = await self.bot.loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL(YTDL_SEARCH_OPTIONS).extract_info(f"ytsearch5:{search}", download=False))
        
        if not info or 'entries' not in info or not info['entries']:
            return await safe_reply(ctx, "❌ No results found.", ephemeral=True)
            
        view = MusicSelectionView(info['entries'], ctx, vc, self.bot)
        await safe_reply(ctx, "🔎 **Select a track:**", view=view)

    @discord.slash_command(name="queue", description="Show music queue")
    async def queue(self, ctx):
        if ctx.guild.id not in self.bot.audio_queues or not self.bot.audio_queues[ctx.guild.id]:
            return await safe_reply(ctx, "Queue is empty.")
        lines = [f"{i+1}. {title}" for i, (url, title) in enumerate(self.bot.audio_queues[ctx.guild.id])]
        await safe_reply(ctx, "\n".join(lines[:10]))

    @discord.slash_command(name="skip", description="Skip song")
    @dj_or_admin()
    async def skip(self, ctx):
        if ctx.guild.voice_client: ctx.guild.voice_client.stop()
        await safe_reply(ctx, "⏭️ Skipped.")

    @discord.slash_command(name="stop", description="Stop music")
    @dj_or_admin()
    async def stop(self, ctx):
        if ctx.guild.id in self.bot.audio_queues: self.bot.audio_queues[ctx.guild.id].clear()
        if ctx.guild.voice_client: ctx.guild.voice_client.stop()
        await safe_reply(ctx, "⏹️ Stopped.")

    @discord.slash_command(name="join", description="Join VC")
    @dj_or_admin()
    async def join(self, ctx):
        await ensure_voice_simple(ctx)
        await safe_reply(ctx, "✅ Joined.")

def setup(bot):
    bot.add_cog(MusicCog(bot))
