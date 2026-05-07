# cogs/audit_logs.py
import asyncio
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
        
        # Grant button
        b = Button(label="Grant Minion", style=discord.ButtonStyle.success, emoji="✅")
        b.callback = self.grant
        self.add_item(b)
        
        # App deep link to profile (avoids web browser refresh loop)
        profile_btn = Button(
            label="View Profile (App)", 
            url=f"discord://-/users/{target_member_id}", 
            style=discord.ButtonStyle.link,
            emoji="🔍"
        )
        self.add_item(profile_btn)
        
    async def grant(self, i):
        try:
            m = i.guild.get_member(self.target)
            r = i.guild.get_role(ROLE_MINION_ID)
            if m and r: 
                await m.add_roles(r)
                await i.response.send_message(f"✅ Minion role granted to **{m.display_name}**.", ephemeral=True)
            else: 
                await i.response.send_message("❌ Error: Member may have left or role is missing.", ephemeral=True)
        except discord.Forbidden:
            await i.response.send_message("❌ Error: I lack permission to grant this role.", ephemeral=True)
        except Exception as e:
            await i.response.send_message(f"⚠️ Error: {e}", ephemeral=True)

class DepartureView(View):
    def __init__(self, target_member_id):
        super().__init__(timeout=None)
        # App deep link to profile (avoids web browser refresh loop)
        profile_btn = Button(
            label="View Profile (App)", 
            url=f"discord://-/users/{target_member_id}", 
            style=discord.ButtonStyle.link,
            emoji="🔍"
        )
        self.add_item(profile_btn)

# --- COG LOGIC ---
class AuditLogsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _get_mod(self, guild, action_type, target):
        await asyncio.sleep(1.5)
        try:
            now = datetime.now(timezone.utc)
            async for entry in guild.audit_logs(limit=3, action=action_type):
                if (now - entry.created_at).total_seconds() < 6:
                    if action_type in [discord.AuditLogAction.member_move, discord.AuditLogAction.member_disconnect]:
                        return entry.user
                    elif entry.target and entry.target.id == target.id:
                        return entry.user
        except: pass
        return None

    @commands.Cog.listener()
    async def on_member_join(self, member):
        try:
            ch = self.bot.get_channel(ARRIVALS_THREAD_ID) or await self.bot.fetch_channel(ARRIVALS_THREAD_ID)
            if not ch: return
            
            created_ts = int(member.created_at.timestamp())
            avatar_url = member.display_avatar.url if member.display_avatar else member.default_avatar.url
            
            em = discord.Embed(
                title="🛬 New Arrival",
                description=f"Welcome to **{member.guild.name}**, {member.mention}!",
                color=THEME_PRIMARY
            )
            em.set_thumbnail(url=avatar_url)
            em.add_field(name="👤 Username", value=f"`{member.name}`", inline=True)
            em.add_field(name="🆔 User ID", value=f"`{member.id}`", inline=True)
            em.add_field(name="📅 Account Created", value=f"<t:{created_ts}:R>", inline=False)
            
            await ch.send(embed=em, view=MinionView(member.id))
        except Exception as e:
            print(f"⚠️ Exception in on_member_join routing: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member):
        try:
            channel = member.guild.get_channel(DEPARTURES_THREAD_ID) or await member.guild.fetch_channel(DEPARTURES_THREAD_ID)
            if not channel: return
            
            title = "👋 Member Left"
            description = f"{member.mention} has left **{member.guild.name}**."
            color = THEME_LOSS 
            now = datetime.now(timezone.utc)
            
            try:
                async for entry in member.guild.audit_logs(limit=1, action=discord.AuditLogAction.kick):
                    if entry.target.id == member.id and (now - entry.created_at).total_seconds() < 10:
                        title = "🥾 Member Kicked"
                        description = f"{member.mention} was kicked from the server.\n**By:** {entry.user.mention} (`{entry.user.name}`)"
                        break
            except: pass

            created_ts = int(member.created_at.timestamp())
            joined_ts = int(member.joined_at.timestamp()) if member.joined_at else None
            avatar_url = member.display_avatar.url if member.display_avatar else member.default_avatar.url

            embed = discord.Embed(title=title, description=description, color=color, timestamp=now)
            embed.set_thumbnail(url=avatar_url)
            embed.add_field(name="👤 Username", value=f"`{member.name}`", inline=True)
            embed.add_field(name="🆔 User ID", value=f"`{member.id}`", inline=True)
            embed.add_field(name="📅 Account Created", value=f"<t:{created_ts}:R>", inline=False)
            if joined_ts:
                embed.add_field(name="📥 Joined Server", value=f"<t:{joined_ts}:R>", inline=True)
                
            embed.set_footer(text=f"User ID: {member.id}")
            
            await channel.send(embed=embed, view=DepartureView(member.id))
        except Exception as e:
            print(f"⚠️ Exception in on_member_remove routing: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        channel = self.bot.get_channel(VOICE_AUDIT_CHANNEL_ID)
        if not channel:
            try: channel = await self.bot.fetch_channel(VOICE_AUDIT_CHANNEL_ID)
            except: return

        actions = []
        color = THEME_PRIMARY

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

        if before.mute != after.mute:
            mod = await self._get_mod(member.guild, discord.AuditLogAction.member_update, member)
            mod_text = f" *(by {mod.mention})*" if mod else ""
            if after.mute:
                actions.append(f"🔇 Server Muted{mod_text}"); color = THEME_LOSS
            else:
                actions.append(f"🔊 Server Unmuted{mod_text}"); color = THEME_WIN
        
        if before.deaf != after.deaf:
            mod = await self._get_mod(member.guild, discord.AuditLogAction.member_update, member)
            mod_text = f" *(by {mod.mention})*" if mod else ""
            if after.deaf:
                actions.append(f"🔕 Server Deafened{mod_text}"); color = THEME_LOSS
            else:
                actions.append(f"🔔 Server Undeafened{mod_text}"); color = THEME_WIN

        if before.self_mute != after.self_mute:
            if after.self_mute: actions.append("🎙️ Muted Mic (Self)")
            else: actions.append("🎙️ Unmuted Mic (Self)")
                
        if before.self_deaf != after.self_deaf:
            if after.self_deaf: actions.append("🎧 Deafened (Self)")
            else: actions.append("🎧 Undeafened (Self)")

        if actions:
            embed = discord.Embed(description="\n".join(actions), color=color, timestamp=datetime.now(timezone.utc))
            embed.set_author(name=f"{member.display_name} Voice Update", icon_url=member.display_avatar.url if member.display_avatar else None)
            embed.set_footer(text=f"User ID: {member.id}")
            try: await channel.send(embed=embed)
            except: pass

def setup(bot):
    bot.add_cog(AuditLogsCog(bot))
