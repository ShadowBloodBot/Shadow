import os
import json
import asyncio
import traceback
from pathlib import Path
from typing import Set

import discord
from discord import ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands
from discord.utils import get

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
ROLE_ADMIN_ID = 1214794734770323466 
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
def _to_sans_bold_italic(text: str) -> str:
    _map = {"A": "𝘼", "B": "𝘽", "C": "𝘾", "D": "𝘿", "E": "𝙀", "F": "𝙁", "G": "𝙂", "H": "𝙃", "I": "𝙄", "J": "𝙅", "K": "𝙆", "L": "𝙇", "M": "𝙈", "N": "𝙉", "O": "𝙊", "P": "𝙋", "Q": "𝙌", "R": "𝙍", "S": "𝙎", "T": "𝙏", "U": "𝙐", "V": "𝙑", "W": "𝙒", "X": "𝙓", "Y": "𝙔", "Z": "𝙕", "a": "𝙖", "b": "𝙗", "c": "𝙘", "d": "𝙙", "e": "𝙚", "f": "𝙛", "g": "𝙜", "h": "𝙝", "i": "𝙞", "j": "𝙟", "k": "𝙠", "l": "𝙡", "m": "𝙢", "n": "𝙣", "o": "𝙤", "p": "𝙥", "q": "𝙦", "r": "𝙧", "s": "s", "t": "𝙩", "u": "𝙪", "v": "𝙫", "w": "𝙬", "x": "𝙭", "y": "𝙮", "z": "𝙯"}
    return "".join(_map.get(ch, ch) for ch in text)

def _limit_channel_name(name: str, limit: int = 100) -> str:
    return name[:limit] if len(name) > limit else name

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

class DynamicRoleRestrictSelect(Select):
    def __init__(self, vc, creator, guild):
        self.vc = vc
        self.creator = creator
        options = [SelectOption(label="Everyone (default)", value="everyone")]
        # Dynamically fetch roles at the time of invocation
        roles = sorted([r for r in guild.roles if r != guild.default_role and not r.managed], key=lambda r: r.position, reverse=True)[:24]
        for r in roles: options.append(SelectOption(label=(r.name or "Role")[:100], value=str(r.id)))
        super().__init__(placeholder="Select a role to restrict...", options=options, min_values=1, max_values=1, custom_id="dynamic_restrict_role_select")

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
        except Exception as e: await interaction.response.send_message(f"❌ Failed: {e}", ephemeral=True)

class DynamicRoleRestrictView(View):
    def __init__(self, vc, creator, guild):
        super().__init__(timeout=60)
        self.add_item(DynamicRoleRestrictSelect(vc, creator, guild))

class VCControlPanel(View):
    def __init__(self, vc, creator):
        super().__init__(timeout=None)
        self.vc = vc; self.creator = creator

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
        
    @discord.ui.button(label="🛡️ Restrict", style=ButtonStyle.primary, custom_id="restrict_vc_btn")
    async def restrict(self, button, i):
        if not await self._check(i): return
        await i.response.send_message("Select a role to restrict this VC to:", view=DynamicRoleRestrictView(self.vc, self.creator, i.guild), ephemeral=True)

    @discord.ui.button(label="❌ Delete", style=ButtonStyle.red, custom_id="delete_vc")
    async def delete(self, button, i):
        if not await self._check(i): return
        await self.vc.delete(); await i.response.send_message("🗑️ Deleted.", ephemeral=True)
        
    @discord.ui.button(label="✏️ Rename", style=ButtonStyle.blurple, custom_id="rename_vc")
    async def rename(self, button, i):
        if not await self._check(i): return
        await i.response.send_message("Please submit the new name.", view=None, ephemeral=True) # Send modal requires no deferring prior, ensuring safe invocation
        await i.response.send_modal(VCNameModal(self.vc))
        
    @discord.ui.button(label="👢 Kick", style=ButtonStyle.gray, custom_id="kick_members")
    async def kick(self, button, i):
        if not await self._check(i): return
        m = [m for m in self.vc.members if m != i.guild.me]
        if not m: return await i.response.send_message("⚠️ No one to kick.", ephemeral=True)
        await i.response.send_message("Select:", view=KickMemberView(self.vc, m), ephemeral=True)
        
    @discord.ui.select(placeholder="Bitrate", options=[SelectOption(label="64k", value="64000"), SelectOption(label="384k", value="384000")], custom_id="bitrate_select")
    async def bitrate(self, select, i):
        if not await self._check(i): return
        try: await self.vc.edit(bitrate=int(select.values[0])); await i.response.send_message(f"📶 Set.", ephemeral=True)
        except: await i.response.send_message("❌ Failed.", ephemeral=True)
        
    @discord.ui.select(placeholder="Limit", options=[SelectOption(label="Unl", value="0"), SelectOption(label="5", value="5"), SelectOption(label="10", value="10")], custom_id="limit_select")
    async def limit(self, select, i):
        if not await self._check(i): return
        try: await self.vc.edit(user_limit=int(select.values[0])); await i.response.send_message(f"👥 Set.", ephemeral=True)
        except: await i.response.send_message("❌ Failed.", ephemeral=True)


class JTCCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_temp_vcs = _load_active_vcs()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        
        # --- JTC LOGIC ---
        if after.channel and after.channel.id == JOIN_TO_CREATE_CHANNEL_ID:
            try:
                cat = get(guild.categories, id=VC_CATEGORY_ID) or after.channel.category
                new_vc = await guild.create_voice_channel(
                    name=_limit_channel_name(_to_sans_bold_italic(f"{member.display_name}'s Room")), 
                    category=cat, bitrate=VC_DEFAULT_BITRATE
                )
                await new_vc.set_permissions(member, connect=True, speak=True)
                self.active_temp_vcs.add(new_vc.id); _save_active_vcs(self.active_temp_vcs)
                await member.move_to(new_vc)
                
                async def send_control_panel(vc, member):
                    await asyncio.sleep(1)
                    embed = discord.Embed(title="🎛️ Voice Control", description=f"Manage **{vc.name}**", color=THEME_PRIMARY)
                    try: await vc.send(embed=embed, view=VCControlPanel(vc, member))
                    except: pass
                asyncio.create_task(send_control_panel(new_vc, member))
            except Exception as e: traceback.print_exc()
                
        # --- CLEANUP LOGIC ---
        if before.channel and before.channel.id in self.active_temp_vcs and len(before.channel.members) == 0:
            try: 
                await before.channel.delete()
                self.active_temp_vcs.discard(before.channel.id)
                _save_active_vcs(self.active_temp_vcs)
            except: pass

def setup(bot):
    bot.add_cog(JTCCog(bot))
