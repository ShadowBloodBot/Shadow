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

# --- FTC ENGINE CLASSES ---
class FTCEditModal(Modal):
    def __init__(self, view, mode):
        super().__init__(title="Edit Savings" if mode == "savings" else "Edit Purchase Price")
        self.view_ref = view
        self.mode = mode
        val = str(view.savings or "") if mode == "savings" else str(view.price or "")
        self.add_item(TextInput(label="Amount ($)", placeholder="e.g., 85000", value=val, required=False))

    async def callback(self, interaction: Interaction):
        from .utility import generate_ftc_embed # Safe self-import
        raw = self.children[0].value.replace(",", "").replace("$", "").strip()
        try: val = int(raw) if raw else None
        except: return await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
            
        if self.mode == "savings": self.view_ref.savings = val
        else: self.view_ref.price = val
            
        embed = generate_ftc_embed(self.view_ref.savings, self.view_ref.price, self.view_ref.state, self.view_ref.fhb)
        await interaction.response.edit_message(embed=embed, view=self.view_ref)

class FTCStateSelect(discord.ui.Select):
    def __init__(self, current_state):
        options = [discord.SelectOption(label=s, default=(s==current_state)) for s in ["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]]
        super().__init__(placeholder="Change State...", options=options, row=1)
    async def callback(self, interaction: Interaction):
        from .utility import generate_ftc_embed
        self.view.state = self.values[0]
        for opt in self.options: opt.default = (opt.label == self.view.state)
        embed = generate_ftc_embed(self.view.savings, self.view.price, self.view.state, self.view.fhb)
        await interaction.response.edit_message(embed=embed, view=self.view)

class FTCControlView(View):
    def __init__(self, savings, price, state, fhb, user_id):
        super().__init__(timeout=900)
        self.savings = savings; self.price = price; self.state = state; self.fhb = fhb; self.user_id = user_id
        self.add_item(FTCStateSelect(state))
    @discord.ui.button(label="Edit Savings", style=discord.ButtonStyle.primary, emoji="💵", row=0)
    async def edit_sav(self, button, i):
        if i.user.id != self.user_id: return
        await i.response.send_modal(FTCEditModal(self, "savings"))
    @discord.ui.button(label="Edit Price", style=discord.ButtonStyle.primary, emoji="🏠", row=0)
    async def edit_pri(self, button, i):
        if i.user.id != self.user_id: return
        await i.response.send_modal(FTCEditModal(self, "price"))
    @discord.ui.button(label="Toggle FHB", style=discord.ButtonStyle.success, emoji="🔄", row=0)
    async def toggle_fhb(self, button, i):
        if i.user.id != self.user_id: return
        from .utility import generate_ftc_embed
        self.fhb = not self.fhb
        embed = generate_ftc_embed(self.savings, self.price, self.state, self.fhb)
        await i.response.edit_message(embed=embed, view=self)

# --- FTC LOGIC ---
def estimate_stamp_duty(price: float, state: str, fhb: bool) -> float:
    state = state.upper(); sd = 0.0
    if state == "NSW":
        sd = price * 0.04 if price <= 1000000 else price * 0.045
        if fhb:
            if price <= 800000: return 0.0
            elif price <= 1000000: return sd * ((price - 800000) / 200000)
    elif state == "VIC":
        sd = price * 0.055
        if fhb:
            if price <= 600000: return 0.0
            elif price <= 750000: return sd * ((price - 600000) / 150000)
    elif state == "QLD":
        sd = price * 0.035 if price <= 1000000 else price * 0.045
        if fhb:
            if price <= 700000: return 0.0
            elif price <= 800000: return sd * ((price - 700000) / 100000)
    elif state == "WA":
        sd = price * 0.04
        if fhb:
            if price <= 450000: return 0.0
            elif price <= 600000: return sd * ((price - 450000) / 150000)
    elif state == "SA":
        sd = price * 0.045
        if fhb and price <= 650000: return 0.0
    else:
        sd = price * 0.045
        if fhb and price <= 500000: return 0.0
    return sd

def find_max_purchase_price(savings: int, lvr_target: float, state: str, fhb: bool) -> int:
    low = 50000; high = 5000000; best_price = 0; fees = 2500
    for _ in range(50): 
        mid = (low + high) / 2
        dep = mid * (1 - lvr_target)
        sd = estimate_stamp_duty(mid, state, fhb)
        if (dep + sd + fees) <= savings: best_price = mid; low = mid
        else: high = mid
    return int(best_price)

def generate_ftc_embed(savings: Optional[int], price: Optional[int], state: str, fhb: bool) -> discord.Embed:
    fees = 2500; state = state.upper(); fhb_str = "Yes" if fhb else "No"
    if price:
        dep_10 = int(price * 0.10); loan_10 = price - dep_10; lmi_10 = int(loan_10 * 0.02)
        sd_10 = int(estimate_stamp_duty(price, state, fhb)); cash_needed_10 = dep_10 + sd_10 + fees
        dep_20 = int(price * 0.20); cash_needed_20 = dep_20 + sd_10 + fees
        
        desc = f"**Target:** `${price:,.0f}` | **State:** `{state}` | **FHB:** `{fhb_str}`"
        if savings: desc += f" | **Savings:** `${savings:,.0f}`"
        desc += "\n\n**10% Deposit (90% LVR)**\n"
        desc += f"> 💵 **Deposit:** `${dep_10:,.0f}`\n> 🏛️ **Govt & Fees:** `${(sd_10 + fees):,.0f}`\n> 💰 **Cash Needed:** `${cash_needed_10:,.0f}`\n> 📈 **LMI (Capitalized):** `${lmi_10:,.0f}`\n"
        if savings:
            diff_10 = savings - cash_needed_10
            desc += f"> 📊 **Status:** {'🟢 Surplus' if diff_10 >= 0 else '🔴 Shortfall'} `${abs(diff_10):,.0f}`\n"
        
        desc += "\n**20% Deposit (80% LVR)**\n"
        desc += f"> 💵 **Deposit:** `${dep_20:,.0f}`\n> 🏛️ **Govt & Fees:** `${(sd_10 + fees):,.0f}`\n> 💰 **Cash Needed:** `${cash_needed_20:,.0f}`\n> 🚫 **LMI:** Avoided\n"
        if savings:
            diff_20 = savings - cash_needed_20
            desc += f"> 📊 **Status:** {'🟢 Surplus' if diff_20 >= 0 else '🔴 Shortfall'} `${abs(diff_20):,.0f}`\n"
            if diff_20 >= 0: tp = "Great news! You comfortably have the 20% deposit ready, meaning we avoid LMI entirely."
            elif diff_10 >= 0: tp = f"We're a bit short for 20%, but you have the cash to buy right now at 90% LVR if you're happy to capitalize the LMI."
            else: tp = f"We're currently short for this purchase price. We'll need to save another ${abs(diff_10):,.0f} to get into the market at 10%."
            desc += f"\n💬 **Broker Tip:**\n*{tp}*"
        return discord.Embed(title="📊 Funds to Complete", description=desc, color=THEME_GOLD)

    elif savings:
        max_10 = find_max_purchase_price(savings, 0.90, state, fhb); max_20 = find_max_purchase_price(savings, 0.80, state, fhb)
        sd_10 = int(estimate_stamp_duty(max_10, state, fhb)); sd_20 = int(estimate_stamp_duty(max_20, state, fhb))
        dep_10 = int(max_10 * 0.10); dep_20 = int(max_20 * 0.20); lmi_10 = int((max_10 * 0.90) * 0.02)
        
        desc = f"**Savings:** `${savings:,.0f}` | **State:** `{state}` | **FHB:** `{fhb_str}`\n\n"
        desc += f"**Max Power: 10% Deposit (90% LVR)**\n> 🏠 **Max Purchase Price:** `${max_10:,.0f}`\n> 💵 **Deposit:** `${dep_10:,.0f}`\n> 🏛️ **Govt & Fees:** `${(sd_10 + fees):,.0f}`\n> 📈 **LMI (Capitalized):** `${lmi_10:,.0f}`\n\n"
        desc += f"**Max Power: 20% Deposit (80% LVR)**\n> 🏠 **Max Purchase Price:** `${max_20:,.0f}`\n> 💵 **Deposit:** `${dep_20:,.0f}`\n> 🏛️ **Govt & Fees:** `${(sd_20 + fees):,.0f}`\n> 🚫 **LMI:** Avoided\n\n"
        desc += f"💬 **Broker Tip:**\n*With ${savings:,.0f} cash, your absolute max purchase is ${max_10:,.0f} (10% deposit). Or, if you want to avoid LMI, your cap is ${max_20:,.0f}.*"
        return discord.Embed(title="📊 Buying Power Calculator", description=desc, color=THEME_WIN)

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

    @discord.slash_command(name="ftc", description="Interactive FTC & Buying Power Calculator (Owner Only)")
    @owner_only()
    async def ftc(
        self, ctx,
        state: Option(str, description="Australian State", choices=["NSW", "VIC", "QLD", "WA", "SA", "TAS", "ACT", "NT"]),
        savings: Option(int, description="Client savings amount", required=False),
        purchase_price: Option(int, description="Target purchase price", required=False),
        fhb: Option(bool, description="First Home Buyer?", default=False)
    ):
        if not savings and not purchase_price:
            return await safe_reply(ctx, "❌ Provide `savings` or `purchase_price`.", ephemeral=True)
        embed = generate_ftc_embed(savings, purchase_price, state, fhb)
        view = FTCControlView(savings, purchase_price, state, fhb, ctx.author.id)
        await safe_reply(ctx, embed=embed, view=view)

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
