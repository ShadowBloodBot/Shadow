# cogs/utility.py
import os
import json
import random
import re
from pathlib import Path
from datetime import datetime, timezone

import discord
from discord.ext import commands
from discord import Option, Interaction
from discord.ui import Modal, TextInput, View, Button, Select

# --- CONSTANTS & IDS ---
THEME_PRIMARY = 0x2B0B35
THEME_WIN = 0x43B581 
THEME_LOSS = 0xF04747 
THEME_GOLD = 0xFFD700 

ARRIVALS_THREAD_ID = 959629903186259978
ROLE_MINION_ID = 955600021502431233
DEPARTURES_THREAD_ID = 960088192177029140
ROLE_ADMIN_ID = 1214794734770323466 
OWNER_ID = 482463400929263627

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

HASTE_FACTS_STORE = (PERSIST_ROOT / "haste_facts.json")
INVITE_ROLE_STORE = (PERSIST_ROOT / "invite_roles.json")

DEFAULT_HASTE_FACTS = [
    "Haste is a man lover", "Haste feeds knights to spearmen", "Haste is the potato peeler",
    "Haste hates women", "Haste loves fat chicks", "Haste would die for brightwood, bro",
    "Haste is a fitzroy enjoyer", "Haste used to get feudal in 3mins... used to",
    "Haste goes Pro scout", "Haste is in a good mood. Jks.", "Haste loves dating paki protestors",
    "Haste is a lefty greeny", "Haste has no dps", "Haste has beef with a dev of a game with sub 1000 players",
    "Haste cant afford ranger gear so he blames the dev", "Haste thinks Maya is fat",
    "Haste was MIA in Shadow Until Jed showed up", "Everyone prefers Haste over Boet",
    "Everyone likes it when Haste has a break down", "Everyone is scared Haste might get bashed at his restaurant",
    "Haste earns 70k a year and that gives Blood anxiety", "Haste Likes using a bow",
    "Haste doesn't have the muscle mass to carry a real life weapon.",
    "Haste never let go of New world.", "Haste only played Vrising cause he thought the outfits were cute."
]

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

# --- HELPERS ---
def admin_only():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member): return False
        return any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles)
    return commands.check(predicate)

def owner_only():
    def predicate(ctx): return ctx.author.id == OWNER_ID
    return commands.check(predicate)

def format_age(dt):
    if not dt: return "Unknown"
    delta = datetime.now(timezone.utc) - dt
    if delta.days > 365: return f"{delta.days // 365} years ago"
    return f"{delta.days} days ago"

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

# --- CUSTOM EMBEDS CLASS ---
class EasyEmbedModal(Modal):
    def __init__(self, channel, edit_msg=None):
        super().__init__(title="Edit Embed" if edit_msg else "Create Custom Embed")
        self.channel = channel; self.edit_msg = edit_msg
        pre_title = edit_msg.embeds[0].title if edit_msg and edit_msg.embeds else ""
        pre_desc = edit_msg.embeds[0].description if edit_msg and edit_msg.embeds else ""
        pre_foot = edit_msg.embeds[0].footer.text if edit_msg and edit_msg.embeds and edit_msg.embeds[0].footer else ""
        pre_col = str(hex(edit_msg.embeds[0].color.value)).replace("0x", "#") if edit_msg and edit_msg.embeds and edit_msg.embeds[0].color else ""
        self.add_item(TextInput(label="Title", placeholder="Embed Title...", value=pre_title, required=True))
        self.add_item(TextInput(label="Description", placeholder="Main content...", value=pre_desc, style=discord.InputTextStyle.paragraph, required=True))
        self.add_item(TextInput(label="Footer (Optional)", placeholder="Small text at bottom...", value=pre_foot, required=False))
        self.add_item(TextInput(label="Color (Hex)", placeholder="#2B0B35", value=pre_col, required=False))
        
    async def callback(self, interaction: Interaction):
        title = self.children[0].value; desc = self.children[1].value; footer = self.children[2].value; color_raw = self.children[3].value
        try: color = int(color_raw.replace("#", ""), 16) if color_raw else THEME_PRIMARY
        except: color = THEME_PRIMARY
        embed = discord.Embed(title=title, description=desc, color=color)
        if footer: embed.set_footer(text=footer)
        if self.edit_msg:
            await self.edit_msg.edit(embed=embed); await interaction.response.send_message("✅ Embed Updated!", ephemeral=True)
        else:
            await self.channel.send(embed=embed); await interaction.response.send_message("✅ Embed Sent!", ephemeral=True)

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
            await i.response.send_message(f"✅ Granted.", ephemeral=True)
        else: 
            await i.response.send_message("❌ Error.", ephemeral=True)

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_haste_facts = []
        self._load_data()

    def _load_data(self):
        if HASTE_FACTS_STORE.exists():
            try: self.active_haste_facts = json.loads(HASTE_FACTS_STORE.read_text())
            except: self.active_haste_facts = list(DEFAULT_HASTE_FACTS)
        else: self.active_haste_facts = list(DEFAULT_HASTE_FACTS)

    @discord.slash_command(name="send_custom", description="Send a clean embed message")
    @admin_only()
    async def send_custom(self, ctx, channel: Option(discord.TextChannel, required=False)):
        target = channel or ctx.channel
        await ctx.send_modal(EasyEmbedModal(target))

    @discord.slash_command(name="edit_custom", description="Edit an existing bot embed")
    @admin_only()
    async def edit_custom(self, ctx, message_id: str, channel: Option(discord.TextChannel, required=False)):
        target_channel = channel or ctx.channel
        try:
            msg = await target_channel.fetch_message(int(message_id))
            if msg.author != self.bot.user: return await ctx.respond("❌ I can only edit my own messages.", ephemeral=True)
            await ctx.send_modal(EasyEmbedModal(target_channel, edit_msg=msg))
        except Exception as e: await ctx.respond(f"❌ Error finding message: {e}", ephemeral=True)

    @discord.slash_command(name="haste", description="Random Haste Fact")
    async def haste(self, ctx):
        if not self.active_haste_facts: return await safe_reply(ctx, "No facts yet.")
        await safe_reply(ctx, f"🍌 **Fact:** {random.choice(self.active_haste_facts)}")

    @discord.slash_command(name="morehaste", description="Add Haste Fact")
    @admin_only()
    async def morehaste(self, ctx, fact: str):
        self.active_haste_facts.append(fact)
        _atomic_write(HASTE_FACTS_STORE, self.active_haste_facts)
        await safe_reply(ctx, "✅ Added.")

    @commands.Cog.listener()
    async def on_member_join(self, member):
        ch = self.bot.get_channel(ARRIVALS_THREAD_ID)
        if ch:
            em = discord.Embed(description=f"{member.mention} joined **{member.guild.name}**", color=THEME_PRIMARY)
            em.set_author(name=str(member), icon_url=member.display_avatar.url if member.display_avatar else None)
            em.set_footer(text="Tap to grant Minion")
            await ch.send(embed=em, view=MinionView(member.id))

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
                    color = 0xF04747 
                    break
        except: pass

        embed = discord.Embed(title=title, color=color, timestamp=now)
        embed.add_field(name="User", value=f"{member.mention}\n{member.name}", inline=False)
        embed.add_field(name="Account Age", value=format_age(member.created_at), inline=True)
        embed.add_field(name="Details", value=description, inline=False)
        embed.set_footer(text=f"ID: {member.id}")
        await channel.send(embed=embed)


def setup(bot):
    bot.add_cog(UtilityCog(bot))
