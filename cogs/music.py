# cogs/music.py
import os
import json
import asyncio
import traceback
from pathlib import Path
from typing import Set
from collections import deque
import discord
from discord import Option, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands
from discord.utils import get
import yt_dlp

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
ROLE_ADMIN_ID = 1214794734770323466 
ROLE_DJ_ID = 955600320287887400
MASTER_OWNERS = [132451058961219584, 482463400929263627]
ADMIN_ROLE_NAME = "SHADOW"

JOIN_TO_CREATE_CHANNEL_ID = 1398618132788281364
VC_CATEGORY_ID = 908659586536468542
VC_DEFAULT_BITRATE = 64000 

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

ACTIVE_VCS_STORE = (PERSIST_ROOT / "active_vcs.json")

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e: print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _load_active_vcs() -> Set[int]:
    if ACTIVE_VCS_STORE.exists():
        try: return set(json.loads(ACTIVE_VCS_STORE.read_text()))
        except: return set()
    return set()

def _save_active_vcs(vcs: Set[int]) -> None:
    _atomic_write(ACTIVE_VCS_STORE, vcs)

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
    user = ctx.user if isinstance(ctx, discord.Interaction) else ctx.author
    if not user.voice or not user.voice.channel:
        await safe_reply(ctx, "❌ Join a VC first!", ephemeral=True); return None
    channel = user.voice.channel; vc = ctx.guild.voice_client
    try:
        if vc and not vc.is_connected():
            try: await vc.disconnect(force=True)
            except: pass
            vc = None
        if vc:
            if vc.channel.id != channel.id: await vc.move_to(channel)
        else: vc = await channel.connect(timeout=10, reconnect=True)
        return vc
    except Exception as e: await safe_reply(ctx, f"❌ Voice Error: {e}", ephemeral=True); return None

def _to_sans_bold_italic(text: str) -> str:
    _map = {"A": "𝘼", "B": "𝘽", "C": "𝘾", "D": "𝘿", "E": "𝙀", "F": "𝙁", "G": "𝙂", "H": "𝙃", "I": "𝙄", "J": "𝙅", "K": "𝙆", "L": "𝙇", "M": "𝙈", "N": "𝙉", "O": "𝙊", "P": "𝙋", "Q": "𝙌", "R": "𝙍", "S": "𝙎", "T": "𝙏", "U": "𝙐", "V": "𝙑", "W": "𝙒", "X": "𝙓", "Y": "𝙔", "Z": "𝙕", "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜", "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣", "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "s", "t": "𝙩", "u": "𝙪", "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯"}
    return "".join(_map.get(ch, ch) for ch in text)

def _limit_channel_name(name: str, limit: int = 100) -> str:
    return name[:limit] if len(name) > limit else name

# --- MUSIC LOGIC ---
YTDL_PLAY_OPTIONS = {'format': 'bestaudio/best', 'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s', 'restrictfilenames': True, 'noplaylist': True, 'nocheckcertificate': True, 'ignoreerrors': False, 'logtostderr': False, 'quiet': True, 'no_warnings': True, 'default_search': 'auto', 'source_address': '0.0.0.0', 'socket_timeout': 10, 'retries': 5}
YTDL_SEARCH_OPTIONS = YTDL_PLAY_OPTIONS.copy()
YTDL_SEARCH_OPTIONS.update({'extract_flat': True, 'skip_download': True})
FFMPEG_OPTIONS = {'options': '-vn', 'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5'}
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
    except Exception as e: print(f"[Music] Error: {e}")

class MusicSelect(Select):
    def __init__(self, entries, ctx, vc, bot):
        self.ctx = ctx; self.vc = vc; self.entries = entries; self.bot = bot
        options = [SelectOption(label=f"{i+1}. {e.get('title', 'Unknown')[:90]}", value=str(i)) for i, e in enumerate(entries[:5])]
        super().__init__(placeholder="Select a track...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.ctx.author.id: return await interaction.response.send_message("❌ Not your request.", ephemeral=True)
        await interaction.response.defer()
        selected = self.entries[int(self.values[0])]; url = selected.get('url') or selected.get('webpage_url'); title = selected.get('title')
        if not url: return await interaction.followup.send("❌ Error: Could not resolve URL.")

        if self.vc.is_playing():
            if self.ctx.guild.id not in self.bot.audio_queues: self.bot.audio_queues[self.ctx.guild.id] = deque()
            self.bot.audio_queues[self.ctx.guild.id].append((url, title))
            await interaction.followup.send(f"📝 **Queued:** {title}")
        else:
            await interaction.followup.send(f"▶️ **Playing:** {title}")
            await play_track(self.bot, self.vc, url, title, self.ctx.guild.id)
        try: await interaction.message.delete()
        except: pass

class MusicSelectionView(View):
    def __init__(self, entries, ctx, vc, bot):
        super().__init__(timeout=60); self.add_item(MusicSelect(entries, ctx, vc, bot))

# --- VOICEMASTER UI ---
class VCNameModal(Modal):
    def __init__(self, vc):
        super().__init__(title="Rename Voice Channel")
        self.vc = vc; self.add_item(TextInput(label="New VC Name", placeholder="Enter name...", required=True, max_length=50))
    async def callback(self, interaction: Interaction):
        try: await self.vc.edit(name=self.children[0].value); await interaction.response.send_message(f"✅ Renamed.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberDropdown(Select):
    def __init__(self, vc, members):
        options = [SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        super().__init__(placeholder="Select member to kick...", options=options, min_values=1, max_values=1); self.vc = vc
    async def callback(self, interaction: Interaction):
        try:
            member = self.vc.guild.get_member(int(self.values[0]))
            if member and member in self.vc.members: await member.move_to(None); await interaction.response.send_message(f"👢 Kicked {member.display_name}.", ephemeral=True)
            else: await interaction.response.send_message("⚠️ Member not found.", ephemeral=True)
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class KickMemberView(View):
    def __init__(self, vc, members):
        super().__init__(timeout=30); self.add_item(KickMemberDropdown(vc, members))

class RoleRestrictSelect(Select):
    def __init__(self, vc, creator):
        self.vc = vc; self.creator = creator
        options = [SelectOption(label="Everyone (default)", value="everyone")]
        roles = sorted([r for r in vc.guild.roles if r != vc.guild.default_role and not r.managed], key=lambda r: r.position, reverse=True)[:24]
        for r in roles: options.append(SelectOption(label=(r.name or "Role")[:100], value=str(r.id)))
        super().__init__(placeholder="Restrict VC...", options=options, min_values=1, max_values=1, custom_id="restrict_role_select")
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.creator.id: return await interaction.response.send_message("🚫 Only creator.", ephemeral=True)
        try:
            if self.values[0] == "everyone":
                await self.vc.set_permissions(interaction.guild.default_role, connect=None)
                if self.vc.category:
                    for target, overwrite in self.vc.category.overwrites.items():
                        if isinstance(target, discord.Role) and target != interaction.guild.default_role:
                            await self.vc.set_permissions(target, connect=None)
                await interaction.response.send_message("✅ Restriction cleared.", ephemeral=True)
            else:
                role = interaction.guild.get_role(int(self.values[0]))
                if role:
                    await self.vc.set_permissions(interaction.guild.default_role, connect=False)
                    await self.vc.set_permissions(role, connect=True); await self.vc.set_permissions(self.creator, connect=True)
                    for oid in MASTER_OWNERS:
                        owner = interaction.guild.get_member(oid)
                        if owner: await self.vc.set_permissions(owner, connect=True)
                    if self.vc.category:
                        for target, overwrite in self.vc.category.overwrites.items():
                            if isinstance(target, discord.Role) and target != interaction.guild.default_role and target.id != role.id and not target.permissions.administrator:
                                await self.vc.set_permissions(target, connect=False)
                    await interaction.response.send_message(f"🔐 Restricted to {role.name}.", ephemeral=True)
        except: await interaction.response.send_message("❌ Failed.", ephemeral=True)

class VCControlPanel(View):
    def __init__(self, vc, creator):
        super().__init__(timeout=None)
        self.vc = vc; self.creator = creator
        try: self.add_item(RoleRestrictSelect(vc, creator))
        except: pass
    async def _check(self, i):
        if i.user.id == self.creator.id: return True
        if i.data.get("custom_id") == "delete_vc" and any(r.name == ADMIN_ROLE_NAME or r.id == ROLE_ADMIN_ID for r in i.user.roles): return True
        await i.response.send_message("🚫 Only creator.", ephemeral=True); return False
    @discord.ui.button(label="🔒 Lock", style=ButtonStyle.danger, custom_id="lock_vc")
    async def lock(self, button, i):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        for m in self.vc.members: await self.vc.set_permissions(m, connect=True)
        for oid in MASTER_OWNERS:
            owner = i.guild.get_member(oid)
            if owner and owner not in self.vc.members: await self.vc.set_permissions(owner, connect=True)
        await self.vc.set_permissions(i.guild.default_role, connect=False)
        if self.vc.category:
            for target, overwrite in self.vc.category.overwrites.items():
                if isinstance(target, discord.Role) and target != i.guild.default_role and not target.permissions.administrator:
                    await self.vc.set_permissions(target, connect=False)
        await i.followup.send("🔒 Locked securely.", ephemeral=True)
    @discord.ui.button(label="🔓 Unlock", style=ButtonStyle.success, custom_id="unlock_vc")
    async def unlock(self, button, i):
        if not await self._check(i): return
        await i.response.defer(ephemeral=True)
        await self.vc.set_permissions(i.guild.default_role, connect=None)
        if self.vc.category:
            for target, overwrite in self.vc.category.overwrites.items():
                if isinstance(target, discord.Role) and target != i.guild.default_role: await self.vc.set_permissions(target, connect=None)
        await i.followup.send("🔓 Unlocked.", ephemeral=True)
    @discord.ui.button(label="❌ Delete", style=
