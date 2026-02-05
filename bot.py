# bot.py — ShadowSyn Unified System
#
# === MODULES INCLUDED ===
# 1. ShadowSyn Core (Welcome, Speak, Audit, Departures, Roles)
# 2. VoiceMaster (Join-to-Create, Dynamic VCs, Control Panel)
#
# Env: DISCORD_TOKEN
# Persistence: role_picker.json, active_vcs.json

import os
import re
import json
import asyncio
import tempfile
import time
from pathlib import Path
from typing import Optional, Tuple, Union, Dict, List, Set
from datetime import datetime, timezone

import discord
from discord import app_commands, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select, button, select
from gtts import gTTS
from shutil import which
from googletrans import Translator
import aiohttp
from discord.utils import get

# =========================== CONSTANTS ===========================

VANITY_INVITE  = "https://discord.gg/shadowsyn"
THEME_PRIMARY  = 0x2B0B35

ARRIVALS_THREAD_ID      = 959629903186259978
ROLE_MINION_ID          = 955600021502431233
ROLE_ADMIN_ID           = 1214794734770323466
ROLE_MEMBER_ID          = 955600320287883314
AUDIT_LOG_CHANNEL_ID    = 1215000049445101669

VOICE_HUB_CHANNEL_ID    = 1214795362947039232
VOICE_CATEGORY_ID       = 1214795058692358174

# =========================== DATA PERSISTENCE ===========================

def load_json(fp: str, default: dict) -> dict:
    if not os.path.exists(fp): return default
    try:
        with open(fp, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(fp: str, data: dict):
    with open(fp, "w", encoding="utf-8") as f: json.dump(data, f, indent=4)

ROLE_PICKER_FILE = "role_picker.json"
ACTIVE_VCS_FILE  = "active_vcs.json"

# =========================== UTILS ===========================

def admin_only():
    async def predicate(interaction: discord.Interaction):
        if interaction.user.guild_permissions.administrator: return True
        admin_role = interaction.guild.get_role(ROLE_ADMIN_ID)
        if admin_role in interaction.user.roles: return True
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return False
    return app_commands.check(predicate)

async def safe_defer(interaction: Interaction, ephemeral=False):
    try: await interaction.response.defer(ephemeral=ephemeral)
    except: pass

async def safe_reply(interaction: Interaction, content: str, ephemeral=False):
    try:
        if interaction.response.is_done(): await interaction.followup.send(content, ephemeral=ephemeral)
        else: await interaction.response.send_message(content, ephemeral=ephemeral)
    except: pass

# =========================== ROLE PICKER LOGIC ===========================

def get_guild_role_cfg(guild_id: int):
    data = load_json(ROLE_PICKER_FILE, {})
    return data.get(str(guild_id), {"options": [], "panel": None})

def set_guild_role_cfg(guild_id: int, cfg: dict):
    data = load_json(ROLE_PICKER_FILE, {})
    data[str(guild_id)] = cfg
    save_json(ROLE_PICKER_FILE, data)

class DualRolePickerView(View):
    def __init__(self, guild: discord.Guild, options: list):
        super().__init__(timeout=None)
        if not options: return
        
        select_opt = []
        for opt in options:
            role = guild.get_role(int(opt["role_id"]))
            if role:
                select_opt.append(SelectOption(
                    label=opt["label"],
                    description=opt.get("desc", ""),
                    value=str(role.id),
                    emoji=opt.get("emoji")
                ))
        
        if select_opt:
            self.add_item(RoleSelect(select_opt))

class RoleSelect(Select):
    def __init__(self, options):
        super().__init__(
            placeholder="Choose your roles...",
            min_values=0,
            max_values=len(options),
            options=options,
            custom_id="shadowsyn:role_select"
        )

    async def callback(self, interaction: Interaction):
        member = interaction.user
        guild_options = get_guild_role_cfg(interaction.guild.id).get("options", [])
        managed_ids = {int(o["role_id"]) for o in guild_options}
        selected_ids = {int(v) for v in self.values}
        
        to_add = []
        to_remove = []
        
        for rid in managed_ids:
            role = interaction.guild.get_role(rid)
            if not role: continue
            if rid in selected_ids:
                if role not in member.roles: to_add.append(role)
            else:
                if role in member.roles: to_remove.append(role)
        
        if to_add: await member.add_roles(*to_add)
        if to_remove: await member.remove_roles(*to_remove)
        
        await interaction.response.send_message("✅ Roles updated.", ephemeral=True)

# =========================== VOICEMASTER LOGIC ===========================

class VoiceControlView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @button(label="Lock", style=ButtonStyle.grey, custom_id="vm:lock")
    async def lock(self, interaction: Interaction, button: Button):
        await self.toggle_lock(interaction, False)

    @button(label="Unlock", style=ButtonStyle.grey, custom_id="vm:unlock")
    async def unlock(self, interaction: Interaction, button: Button):
        await self.toggle_lock(interaction, True)

    @button(label="Hide", style=ButtonStyle.grey, custom_id="vm:hide")
    async def hide(self, interaction: Interaction, button: Button):
        await self.toggle_hide(interaction, False)

    @button(label="Unhide", style=ButtonStyle.grey, custom_id="vm:unhide")
    async def unhide(self, interaction: Interaction, button: Button):
        await self.toggle_hide(interaction, True)

    @button(label="Rename", style=ButtonStyle.blurple, custom_id="vm:rename")
    async def rename(self, interaction: Interaction, button: Button):
        if not await self.is_owner(interaction): return
        await interaction.response.send_modal(VCRenameModal())

    async def is_owner(self, interaction: Interaction):
        data = load_json(ACTIVE_VCS_FILE, {})
        vc_id = str(interaction.user.voice.channel.id) if interaction.user.voice else None
        if vc_id and data.get(vc_id) == interaction.user.id: return True
        await interaction.response.send_message("❌ Only the owner can control this VC.", ephemeral=True)
        return False

    async def toggle_lock(self, interaction: Interaction, state: bool):
        if not await self.is_owner(interaction): return
        ch = interaction.user.voice.channel
        await ch.set_permissions(interaction.guild.default_role, connect=state)
        await interaction.response.send_message(f"VC {'unlocked' if state else 'locked'}.", ephemeral=True)

    async def toggle_hide(self, interaction: Interaction, state: bool):
        if not await self.is_owner(interaction): return
        ch = interaction.user.voice.channel
        await ch.set_permissions(interaction.guild.default_role, view_channel=state)
        await interaction.response.send_message(f"VC {'visible' if state else 'hidden'}.", ephemeral=True)

class VCRenameModal(Modal, title="Rename Voice Channel"):
    name = TextInput(label="New Name", placeholder="My Awesome VC", min_length=1, max_length=32)
    async def on_submit(self, interaction: Interaction):
        await interaction.user.voice.channel.edit(name=self.name.value)
        await interaction.response.send_message(f"Renamed to: {self.name.value}", ephemeral=True)

# =========================== BOT CLASS ===========================

class ShadowSynBot(discord.Client):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        self.add_view(VoiceControlView())
        cfg_data = load_json(ROLE_PICKER_FILE, {})
        for g_id, cfg in cfg_data.items():
            if cfg.get("panel") and cfg.get("options"):
                guild = self.get_guild(int(g_id))
                if guild:
                    self.add_view(DualRolePickerView(guild, cfg["options"]))

    async def on_ready(self):
        print(f"Logged in as {self.user} (ID: {self.user.id})")
        await self.tree.sync()

    async def on_member_join(self, member: discord.Member):
        member_role = member.guild.get_role(ROLE_MEMBER_ID)
        if member_role: await member.add_roles(member_role)
        
        channel = member.guild.get_channel(ARRIVALS_THREAD_ID)
        if channel:
            embed = discord.Embed(title="Welcome to ShadowSyn!", description=f"Glad to have you here, {member.mention}!", color=THEME_PRIMARY)
            embed.set_thumbnail(url=member.display_avatar.url)
            await channel.send(content=member.mention, embed=embed)

    async def on_member_remove(self, member: discord.Member):
        channel = member.guild.get_channel(AUDIT_LOG_CHANNEL_ID)
        if channel:
            await channel.send(f"❌ **{member}** has left the server.")

    async def on_voice_state_update(self, member: discord.Member, before, after):
        if after.channel and after.channel.id == VOICE_HUB_CHANNEL_ID:
            category = member.guild.get_channel(VOICE_CATEGORY_ID)
            new_ch = await member.guild.create_voice_channel(name=f"🔊 {member.name}'s VC", category=category)
            await member.move_to(new_ch)
            data = load_json(ACTIVE_VCS_FILE, {})
            data[str(new_ch.id)] = member.id
            save_json(ACTIVE_VCS_FILE, data)

        if before.channel and before.channel.category_id == VOICE_CATEGORY_ID:
            if before.channel.id != VOICE_HUB_CHANNEL_ID and len(before.channel.members) == 0:
                data = load_json(ACTIVE_VCS_FILE, {})
                if str(before.channel.id) in data:
                    del data[str(before.channel.id)]
                    save_json(ACTIVE_VCS_FILE, data)
                await before.channel.delete()

bot = ShadowSynBot()

# =========================== UPDATED SPEAK COMMAND ===========================

@bot.tree.command(name="speak", description="Translate and speak a message in a voice channel.")
@app_commands.describe(
    text="The message you want to translate and speak",
    language="The language to translate into and speak with"
)
@app_commands.choices(language=[
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Spanish", value="es"),
    app_commands.Choice(name="French", value="fr"),
    app_commands.Choice(name="German", value="de"),
    app_commands.Choice(name="Italian", value="it"),
    app_commands.Choice(name="Japanese", value="ja"),
    app_commands.Choice(name="Russian", value="ru"),
    app_commands.Choice(name="Chinese", value="zh-cn"),
])
async def speak(interaction: discord.Interaction, text: str, language: str):
    if not interaction.user.voice or not interaction.user.voice.channel:
        return await interaction.response.send_message("❌ You must be in a voice channel to use this command.", ephemeral=True)

    await interaction.response.defer()

    try:
        # 1. Translation Step
        translator = Translator()
        loop = asyncio.get_event_loop()
        translation = await loop.run_in_executor(None, lambda: translator.translate(text, dest=language))
        translated_text = translation.text
        
        # 2. TTS Generation
        tts = gTTS(text=translated_text, lang=language)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as fp:
            temp_filename = fp.name
            tts.save(temp_filename)

        # 3. Audio Connection
        vc = interaction.user.voice.channel
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)

        if voice_client and voice_client.is_connected():
            await voice_client.move_to(vc)
        else:
            voice_client = await vc.connect()

        executable = which("ffmpeg")
        if not executable:
            return await interaction.followup.send("❌ FFmpeg not found.")

        audio_source = discord.FFmpegPCMAudio(temp_filename, executable=executable)
        
        if voice_client.is_playing():
            voice_client.stop()
            
        voice_client.play(audio_source, after=lambda e: os.remove(temp_filename))

        await interaction.followup.send(f"🎙️ **Translated to {language}:** {translated_text}")

    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# =========================== OTHER COMMANDS ===========================

@bot.tree.command(name="vc_panel", description="Post the VoiceMaster control panel.")
@admin_only()
async def vc_panel(interaction: Interaction):
    embed = discord.Embed(title="Voice Control Panel", description="Use the buttons below to manage your temporary voice channel.", color=THEME_PRIMARY)
    await interaction.channel.send(embed=embed, view=VoiceControlView())
    await interaction.response.send_message("Panel posted.", ephemeral=True)

def _parse_role_mentions(text: str) -> list:
    return [int(x) for x in re.findall(r'<@&(\d+)>', text)]

def role_picker_embed():
    return discord.Embed(title="Role Selection", description="Pick your roles from the dropdown menu below.", color=THEME_PRIMARY)

@admin_only()
@bot.tree.command(name="roles_setup", description="Post the role picker panel.")
async def roles_setup(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    cfg = get_guild_role_cfg(interaction.guild.id)
    view = DualRolePickerView(interaction.guild, cfg.get("options", []))
    msg = await interaction.channel.send(embed=role_picker_embed(), view=view)
    cfg["panel"] = {"channel_id": msg.channel.id, "message_id": msg.id}
    set_guild_role_cfg(interaction.guild.id, cfg)
    await safe_reply(interaction, "✅ Panel setup.", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_add", description="Add roles to the picker.")
async def roles_add(interaction: discord.Interaction, roles: str, labels: str, emojis: Optional[str] = None):
    await safe_defer(interaction, ephemeral=True)
    ids = _parse_role_mentions(roles)
    lbls = [l.strip() for l in labels.split(",")]
    emjs = [e.strip() for e in emojis.split(",")] if emojis else []
    cfg = get_guild_role_cfg(interaction.guild.id)
    for i, rid in enumerate(ids):
        cfg["options"].append({
            "role_id": str(rid),
            "label": lbls[i] if i < len(lbls) else f"Role {rid}",
            "emoji": emjs[i] if i < len(emjs) else None
        })
    set_guild_role_cfg(interaction.guild.id, cfg)
    await safe_reply(interaction, f"✅ Added {len(ids)} roles.", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_remove", description="Remove roles from picker.")
async def roles_remove(interaction: discord.Interaction, roles: str):
    await safe_defer(interaction, ephemeral=True)
    ids = set(_parse_role_mentions(roles))
    cfg = get_guild_role_cfg(interaction.guild.id)
    cfg["options"] = [o for o in cfg.get("options", []) if int(o["role_id"]) not in ids]
    set_guild_role_cfg(interaction.guild.id, cfg)
    await safe_reply(interaction, "✅ Removed roles.", ephemeral=True)

@admin_only()
@bot.tree.command(name="roles_sync", description="Refresh panel.")
async def roles_sync(interaction: discord.Interaction):
    await safe_defer(interaction, ephemeral=True)
    cfg = get_guild_role_cfg(interaction.guild.id)
    panel = cfg.get("panel")
    if not panel: return await safe_reply(interaction, "No panel found.", ephemeral=True)
    try:
        ch = interaction.guild.get_channel(panel["channel_id"])
        msg = await ch.fetch_message(panel["message_id"])
        view = DualRolePickerView(interaction.guild, cfg.get("options", []))
        await msg.edit(embed=role_picker_embed(), view=view)
        await safe_reply(interaction, "✅ Synced.", ephemeral=True)
    except: await safe_reply(interaction, "❌ Sync failed.", ephemeral=True)

# =========================== RUN ===========================

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if token:
        bot.run(token)
    else:
        print("Error: DISCORD_TOKEN not found.")
