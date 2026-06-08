"""
InvestBot Cog - Australian Property Investment Community Bot
Mortgage broker lead generation and qualification system
Integrates seamlessly with Shadow bot (py-cord)
"""

import os
import json
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict

import discord
from discord.ext import commands, tasks
from discord import Option, Interaction
from discord.ui import View, Button

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================

THEME_PRIMARY = 0x2B0B35
THEME_SUCCESS = 0x2ecc71
THEME_WARNING = 0xf39c12
ROLE_ADMIN_ID = 1214794734770323466
OWNER_ID = 482463400929263627

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except:
    PERSIST_ROOT = Path(".").resolve()

INVEST_DATA_STORE = PERSIST_ROOT / "invest_data.json"
INVEST_CACHE_STORE = PERSIST_ROOT / "invest_cache.json"

# Default suburb data (fallback)
DEFAULT_SUBURBS = {
    "croydon-park": {
        "median": 720000,
        "growth_1yr": 3.2,
        "yield": 3.8,
        "demand": "strong",
        "investor_score": "high",
        "days_on_market": 28
    },
    "inner-west": {
        "median": 850000,
        "growth_1yr": 2.8,
        "yield": 3.2,
        "demand": "strong",
        "investor_score": "high",
        "days_on_market": 31
    },
    "sutherland-shire": {
        "median": 1100000,
        "growth_1yr": 1.5,
        "yield": 2.9,
        "demand": "moderate",
        "investor_score": "medium",
        "days_on_market": 35
    }
}

OUTREACH_TEMPLATES = {
    "refi": "Hey! Saw you're looking at refinance scenarios. Most investors don't realize they can structure their split loan differently to maximize tax outcomes. Worth a quick chat outside Discord? I do free 15min discovery calls—no pressure. Let me know 👍",
    "first_investor": "You're asking solid questions about negative gearing. That tells me you're thinking long-term, not quick flip. Exactly the investor I help structure strategies for. Free chat sometime this week? Hit me up if keen.",
    "portfolio": "Saw you're mapping out next property. That's the investor mindset I work with. Happy to run the numbers on your scenarios—often saves $10k+ in tax + interest. Chat?"
}

# ==========================================
# UTILITY FUNCTIONS
# ==========================================

def _serialize_for_json(obj):
    """Recursively convert datetime to ISO strings for JSON"""
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj

def _atomic_write(file_path: Path, data):
    """Atomic JSON write - matches utility.py pattern"""
    try:
        clean_data = _serialize_for_json(data)
        content = json.dumps(clean_data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ InvestBot Persistence Error [{file_path.name}]: {e}")

def admin_only():
    """Check if user is admin (matches utility.py)"""
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member):
            return False
        return any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles)
    return commands.check(predicate)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    """Compatible with both Context and Interaction (matches utility.py)"""
    try:
        if hasattr(ctx_or_inter, 'respond'):
            return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            else:
                return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception as e:
        print(f"⚠️ Safe reply error: {e}")
        return None

# ==========================================
# INVEST BOT COG
# ==========================================

class InvestBotCog(commands.Cog):
    """Investment property analysis bot for mortgage broker lead generation"""
    
    def __init__(self, bot):
        self.bot = bot
        self.load_data()
    
    def load_data(self):
        """Load suburbs and leads from disk"""
        if INVEST_DATA_STORE.exists():
            try:
                data = json.loads(INVEST_DATA_STORE.read_text())
                self.suburbs = data.get("suburbs", DEFAULT_SUBURBS.copy())
                self.qualified_leads = data.get("qualified_leads", {})
                self.rba_rate = data.get("rba_rate", 4.35)
            except:
                self.suburbs = DEFAULT_SUBURBS.copy()
                self.qualified_leads = {}
                self.rba_rate = 4.35
        else:
            self.suburbs = DEFAULT_SUBURBS.copy()
            self.qualified_leads = {}
            self.rba_rate = 4.35
            self.save_data()
    
    def save_data(self):
        """Save suburbs and leads to disk"""
        data = {
            "suburbs": self.suburbs,
            "qualified_leads": self.qualified_leads,
            "rba_rate": self.rba_rate
        }
        _atomic_write(INVEST_DATA_STORE, data)
    
    def flag_lead(self, user_id: int, profile_type: str):
        """Flag a user as qualified lead"""
        if str(user_id) not in self.qualified_leads:
            self.qualified_leads[str(user_id)] = {}
        self.qualified_leads[str(user_id)]["profile"] = profile_type
        self.qualified_leads[str(user_id)]["flagged_at"] = datetime.now().isoformat()
        self.save_data()
    
    # ==========================================
    # SLASH COMMANDS
    # ==========================================
    
    @discord.slash_command(name="suburb", description="Analyze a Sydney suburb for investment")
    async def suburb(self, ctx, suburb_name: str):
        """Get suburb investment analysis"""
        suburb_key = suburb_name.lower().replace(" ", "-")
        
        if suburb_key not in self.suburbs:
            available = ", ".join(self.suburbs.keys())
            return await safe_reply(ctx, f"❌ No data for '{suburb_name}'. Available: {available}", ephemeral=True)
        
        data = self.suburbs[suburb_key]
        
        # Auto-flag as lead
        self.flag_lead(ctx.author.id, "researcher")
        
        # Build embed
        score_emoji = "🔥" if data.get("investor_score") == "high" else "🟡"
        demand_emoji = "✅" if data.get("demand") == "strong" else "⚠️"
        
        embed = discord.Embed(
            title=f"🏠 {suburb_name.title()}, NSW",
            description="Investment Analysis",
            color=THEME_PRIMARY
        )
        embed.add_field(name="Median Price", value=f"${data['median']:,}", inline=True)
        embed.add_field(name="1yr Growth", value=f"{data['growth_1yr']}%", inline=True)
        embed.add_field(name="Rental Yield", value=f"{data['yield']}%", inline=True)
        embed.add_field(name=f"Investor Score {score_emoji}", value=data["investor_score"].title(), inline=True)
        embed.add_field(name=f"Demand {demand_emoji}", value=data["demand"].title(), inline=True)
        embed.add_field(name="Days on Market", value=str(data["days_on_market"]), inline=True)
        embed.set_footer(text="Educational discussion only—not financial advice")
        
        await safe_reply(ctx, embed=embed)
    
    @discord.slash_command(name="neggear", description="Calculate negative gearing")
    async def neggear(self, ctx,
                      property_price: Option(int, description="Purchase price (AUD)"),
                      annual_rent: Option(int, description="Annual rental (AUD)"),
                      mortgage_rate: Option(float, description="Mortgage rate (%)")):
        """Calculate negative gearing shortfall and tax benefit"""
        
        self.flag_lead(ctx.author.id, "refinancer")
        
        loan_amount = property_price * 0.8
        annual_interest = loan_amount * (mortgage_rate / 100)
        estimated_expenses = annual_rent * 0.25
        annual_shortfall = (annual_interest + estimated_expenses) - annual_rent
        tax_benefit = annual_shortfall * 0.39
        
        embed = discord.Embed(
            title="💰 Negative Gearing Calculator",
            color=THEME_PRIMARY
        )
        embed.add_field(name="Loan Amount", value=f"${loan_amount:,.0f}", inline=True)
        embed.add_field(name="Annual Interest", value=f"${annual_interest:,.0f}", inline=True)
        embed.add_field(name="Est. Expenses (25%)", value=f"${estimated_expenses:,.0f}", inline=True)
        embed.add_field(name="Annual Rental", value=f"${annual_rent:,}", inline=True)
        embed.add_field(name="🔴 Annual Shortfall", value=f"${annual_shortfall:,.0f}", inline=True)
        embed.add_field(name="💚 Est. Tax Benefit (39%)", value=f"${tax_benefit:,.0f}", inline=True)
        embed.set_footer(text="This is discussion only—not personal financial advice.")
        
        await safe_reply(ctx, embed=embed)
    
    @discord.slash_command(name="refi-check", description="Refinance eligibility check")
    async def refi_check(self, ctx,
                         current_rate: Option(float, description="Current rate (%)"),
                         equity_percent: Option(int, description="Home equity (%)"),
                         annual_income: Option(int, description="Annual income (AUD)")):
        """Quick refinance eligibility and savings estimate"""
        
        self.flag_lead(ctx.author.id, "refinancer")
        
        market_rate = self.rba_rate
        rate_saving = current_rate - market_rate
        estimated_loan = annual_income * 4
        annual_saving = estimated_loan * (rate_saving / 100)
        
        embed = discord.Embed(
            title="🔄 Refinance Eligibility Check",
            color=THEME_SUCCESS if rate_saving > 0 else THEME_WARNING
        )
        embed.add_field(name="Current Rate", value=f"{current_rate}%", inline=True)
        embed.add_field(name="Market Rate (approx)", value=f"{market_rate}%", inline=True)
        embed.add_field(name="Potential Spread", value=f"{rate_saving:.2f}%", inline=True)
        embed.add_field(name="Equity Position", value=f"{equity_percent}%", inline=True)
        embed.add_field(name="Est. Loan Capacity", value=f"${estimated_loan:,}", inline=True)
        embed.add_field(name="💵 Est. Annual Saving", value=f"${annual_saving:,.0f}" if rate_saving > 0 else "Not viable", inline=True)
        embed.set_footer(text="Educational discussion only—not financial advice.")
        
        await safe_reply(ctx, embed=embed)
    
    @discord.slash_command(name="compare", description="Compare two suburbs")
    async def compare(self, ctx, suburb1: str, suburb2: str):
        """Side-by-side suburb comparison"""
        
        s1_key = suburb1.lower().replace(" ", "-")
        s2_key = suburb2.lower().replace(" ", "-")
        
        if s1_key not in self.suburbs or s2_key not in self.suburbs:
            return await safe_reply(ctx, "❌ One or both suburbs not found.", ephemeral=True)
        
        s1 = self.suburbs[s1_key]
        s2 = self.suburbs[s2_key]
        
        self.flag_lead(ctx.author.id, "portfolio_builder")
        
        embed = discord.Embed(
            title="📊 Suburb Comparison",
            color=THEME_PRIMARY
        )
        
        comparison = f"""
**Metric** | **{suburb1.title()}** | **{suburb2.title()}**
---|---|---
Median | ${s1['median']:,} | ${s2['median']:,}
1yr Growth | {s1['growth_1yr']}% | {s2['growth_1yr']}%
Yield | {s1['yield']}% | {s2['yield']}%
Investor Score | {s1['investor_score'].title()} | {s2['investor_score'].title()}
        """
        
        embed.description = comparison
        embed.set_footer(text="Educational discussion only—not financial advice")
        
        await safe_reply(ctx, embed=embed)
    
    @discord.slash_command(name="markets", description="Daily market digest")
    @admin_only()
    async def markets(self, ctx):
        """Post daily market digest"""
        
        sorted_suburbs = sorted(
            self.suburbs.items(),
            key=lambda x: x[1].get('growth_1yr', 0),
            reverse=True
        )
        
        top_movers = "\n".join([
            f"• **{k.replace('-', ' ').title()}**: +{v.get('growth_1yr')}%"
            for k, v in sorted_suburbs[:3]
        ])
        
        embed = discord.Embed(
            title="📈 Daily Market Digest",
            color=THEME_SUCCESS
        )
        embed.add_field(name="🔥 Top Movers (1yr)", value=top_movers, inline=False)
        embed.add_field(name="📊 Current RBA Rate", value=f"{self.rba_rate}%", inline=True)
        embed.add_field(name="💭 Insight", value="Run `/refi-check` to see if you can save.", inline=False)
        embed.set_footer(text="Educational discussion only | Updated daily")
        
        await safe_reply(ctx, embed=embed)
    
    # ==========================================
    # ADMIN COMMANDS
    # ==========================================
    
    @discord.slash_command(name="invest_lead", description="Flag user as qualified lead")
    @admin_only()
    async def invest_lead(self, ctx, user: discord.User, profile_type: str):
        """Manually flag user as qualified"""
        self.flag_lead(user.id, profile_type)
        await safe_reply(ctx, f"✅ Flagged {user.mention} as **{profile_type}** lead.", ephemeral=True)
    
    @discord.slash_command(name="invest_leads", description="List qualified leads")
    @admin_only()
    async def invest_leads(self, ctx):
        """Show all qualified leads"""
        
        if not self.qualified_leads:
            return await safe_reply(ctx, "No leads yet.", ephemeral=True)
        
        embed = discord.Embed(
            title="📋 Qualified Leads",
            color=THEME_SUCCESS
        )
        
        for user_id, lead_data in list(self.qualified_leads.items())[:10]:
            profile = lead_data.get("profile", "Unknown")
            flagged = lead_data.get("flagged_at", "N/A")[:10]
            embed.add_field(
                name=f"User ID: {user_id}",
                value=f"Type: {profile}\nFlagged: {flagged}",
                inline=False
            )
        
        await safe_reply(ctx, embed=embed, ephemeral=True)
    
    @discord.slash_command(name="invest_template", description="Send outreach template")
    @admin_only()
    async def invest_template(self, ctx, user: discord.User, template: str):
        """Send outreach template (refi, first_investor, portfolio)"""
        
        if template not in OUTREACH_TEMPLATES:
            return await safe_reply(ctx, "❌ Invalid template. Use: refi, first_investor, portfolio", ephemeral=True)
        
        try:
            await user.send(OUTREACH_TEMPLATES[template])
            await safe_reply(ctx, f"✅ Sent {template} template to {user.mention}", ephemeral=True)
        except discord.Forbidden:
            await safe_reply(ctx, f"❌ Cannot DM {user.mention}.", ephemeral=True)

# ==========================================
# SETUP
# ==========================================

def setup(bot):
    """Load cog into bot"""
    bot.add_cog(InvestBotCog(bot))
    print("✅ InvestBotCog loaded successfully")
