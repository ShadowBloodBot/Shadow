# cogs/audit_logs.py
import discord
from discord.ext import commands
from discord.ui import View, Button
from datetime import datetime, timezone

# --- CONSTANTS & IDS ---
THEME_PRIMARY = 0x2B0B35
THEME_LOSS = 0xF04747 
THEME_WIN = 0x43B581
THEME_INFO = 0x3498DB

ARRIVALS_THREAD_ID = 959629903186259978
DEPARTURES_THREAD_ID = 960088192177029140
ROLE_MINION_ID = 955600021502431233
VOICE_AUDIT_CHANNEL_ID = 961726632249425930

# --- HELPERS ---
def format_age(dt):
    if not dt: return "Unknown"
    delta = datetime.now(timezone.utc) - dt
    if delta.days > 365: return f"{delta.days // 365} years ago"
    return f"{delta.days} days ago"

# --- VIEWS ---
class MinionView(View):
    def __init__(self, target_member_id):
        super().__init__(timeout=86400)
        self.target = target_member_id
        b = Button(label="Minion", style=discord.ButtonStyle.success)
        b.callback = self.grant
        self.add_item(b)
        
    async def grant(self, i):
        m = i.guild.get_member(self.target)
        r = i.guild.get_role(ROLE_MINION_ID)
        if m and r: 
            await m.add_roles(r)
            await i.response.send_message("✅ Granted.", ephemeral=True)
        else: 
            await i.response.send_message("❌ Error.", ephemeral=True)

# --- COG LOGIC ---
class AuditLogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # --- INTERNAL HELPER FOR AUDIT LOG CROSS-REFERENCING ---
    async def _get_mod(self, guild, action_type, target):
        """Silently scans the audit log to see if a moderator performed this action in the last 5 seconds."""
        try:
            now = datetime.now(timezone.utc)
            async for entry in guild.audit_logs(limit=5, action=action_type):
                if entry.target.id == target.id and (now - entry.created_at).total_seconds() < 5:
                    return entry.user
        except Exception:
            pass
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member):
        ch = self.bot.get_channel(ARRIVALS_THREAD_ID)
        if ch:
            em = discord.Embed(description=f"{member.mention} joined **{member.guild.name}**", color=THEME_PRIMARY)
            em.set_author(name=str(member), icon_url=member.display_avatar.url if member.display_avatar else None)
            em.set_footer(text="Tap to grant Minion")
            try:
                await ch.send(embed=em, view=MinionView(member.id))
            except Exception:
                pass

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        channel = member.guild.get_channel(DEPARTURES_THREAD_ID) or await member.guild.fetch_channel(DEPARTURES_THREAD_ID)
        if not channel: return
        
        title = "👋 Member Left"
        description = f"{member.mention} left the server."
        color = THEME_LOSS 
        now = datetime.now(timezone.utc)
        
        try:
            async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                if entry.target.id == member.id and (now - entry.created_at).total_seconds() < 10:
                    title = "🥾 Member Kicked"
                    description = f"{member.mention} kicked the server.\nBy: **{entry.user.name}** ({entry.user.display_name})"
                    color = THEME_LOSS 
                    break
        except: pass

        embed = discord.Embed(title=title, color=color, timestamp=now)
        embed.add_field(name="User", value=f"{member.mention}\n{member.name}", inline=False)
        embed.add_field(name="Account Age", value=format_age(member.created_at), inline=True)
        embed.add_field(name="Details", value=description, inline=False)
        embed.set_footer(text=f"ID: {member.id}")
        
        try:
            await channel.send(embed=embed)
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        # Fetch the specific audit channel/thread
        channel = self.bot.get_channel(VOICE_AUDIT_CHANNEL_ID)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(VOICE_AUDIT_CHANNEL_ID)
            except Exception:
                return

        actions = []
        color = THEME_PRIMARY

        # 1. Detect Channel Movement & Moderator Disconnects/Moves
        if before.channel != after.channel:
            if before.channel is None:
                actions.append(f"📥 Joined **{after.channel.name}**")
                color = THEME_WIN
            elif after.channel is None:
                mod = await self._get_mod(member.guild, discord.AuditLogAction.member_disconnect, member)
                mod_text = f"\n*(Disconnected by {mod.mention})*" if mod else ""
                actions.append(f"📤 Left **{before.channel.name}**{mod_text}")
                color = THEME_LOSS
            else:
                mod = await self._get_mod(member.guild, discord.AuditLogAction.member_move, member)
                mod_text = f"\n*(Moved by {mod.mention})*" if mod else ""
                actions.append(f"🔄 Moved: **{before.channel.name}** ➡️ **{after.channel.name}**{mod_text}")
                color = THEME_INFO

        # 2. Detect Server Mutes and Deafens (Admin actions)
        if before.mute != after.mute:
            mod = await self._get_mod(member.guild, discord.AuditLogAction.member_update, member)
            mod_text = f" *(by {mod.mention})*" if mod else ""
            if after.mute:
                actions.append(f"🔇 Server Muted{mod_text}")
                color = THEME_LOSS
            else:
                actions.append(f"🔊 Server Unmuted{mod_text}")
                color = THEME_WIN
        
        if before.deaf != after.deaf:
            mod = await self._get_mod(member.guild, discord.AuditLogAction.member_update, member)
            mod_text = f" *(by {mod.mention})*" if mod else ""
            if after.deaf:
                actions.append(f"🔕 Server Deafened{mod_text}")
                color = THEME_LOSS
            else:
                actions.append(f"🔔 Server Undeafened{mod_text}")
                color = THEME_WIN

        # 3. Detect Self Mutes and Deafens (User actions)
        if before.self_mute != after.self_mute:
            if after.self_mute:
                actions.append("🎙️ Muted Mic (Self)")
            else:
                actions.append("🎙️ Unmuted Mic (Self)")
                
        if before.self_deaf != after.self_deaf:
            if after.self_deaf:
                actions.append("🎧 Deafened (Self)")
            else:
                actions.append("🎧 Undeafened (Self)")

        if actions:
            embed = discord.Embed(description="\n".join(actions), color=color, timestamp=datetime.now(timezone.utc))
            embed.set_author(name=f"{member.display_name} Voice Update", icon_url=member.display_avatar.url if member.display_avatar else None)
            embed.set_footer(text=f"User ID: {member.id}")
            
            try:
                await channel.send(embed=embed)
            except Exception:
                pass

def setup(bot):
    bot.add_cog(AuditLogsCog(bot))
