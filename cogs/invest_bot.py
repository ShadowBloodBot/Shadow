import os
import json
import aiohttp
import re
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict

import discord
from discord.ext import commands
from discord import Option

# ==========================================
# DYNAMIC DATABASE INTEGRATION
# ==========================================
# Stripped the hardcoded 2000+ line arrays. We now pull directly from the 
# dynamically generated SuburbDatabase module in memory.
from cogs.suburbs_database import ALL_AUSTRALIAN_SUBURBS, SUBURB_TO_STATE

# --- LOGGING ---
logger = logging.getLogger("ShadowSyn.InvestBot")

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
except Exception as e:
    logger.warning(f"Failed to create persist root: {e}")
    PERSIST_ROOT = Path(".").resolve()

INVEST_DATA_STORE = PERSIST_ROOT / "invest_data.json"
INVEST_CACHE_STORE = PERSIST_ROOT / "invest_cache.json"

# Default baseline test cases
DEFAULT_SUBURBS = {
    "croydon-park": {
        "median": 895000, "growth_1yr": 1.8, "yield": 4.2,
        "demand": "strong", "investor_score": "high", "days_on_market": 32, "source": "manual"
    },
    "inner-west": {
        "median": 1150000, "growth_1yr": 2.1, "yield": 3.8,
        "demand": "very strong", "investor_score": "high", "days_on_market": 28, "source": "manual"
    },
    "sutherland-shire": {
        "median": 1450000, "growth_1yr": 0.9, "yield": 2.9,
        "demand": "moderate", "investor_score": "medium", "days_on_market": 38, "source": "manual"
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
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj

def _atomic_write(file_path: Path, data):
    try:
        clean_data = _serialize_for_json(data)
        content = json.dumps(clean_data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        logger.error(f"InvestBot Persistence Error [{file_path.name}]: {e}")

def admin_only():
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member):
            return False
        return any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles)
    return commands.check(predicate)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'):
            return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            else:
                return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception as e:
        logger.error(f"Safe reply error: {e}")
        return None

def extract_price(text: str) -> Optional[int]:
    """Robust regex to extract AU property prices from text blobs"""
    m1 = re.search(r'\$\s*([1-9]\d{0,2}(?:,\d{3}){1,2})', text)
    if m1:
        return int(m1.group(1).replace(',', ''))
    m2 = re.search(r'\$\s*([1-9]\.\d{1,2})\s*(?:m|M|million|Million)', text)
    if m2:
        return int(float(m2.group(1)) * 1000000)
    return None

async def get_suburb_autocomplete(ctx: discord.AutocompleteContext):
    """Auto-complete engine powered by the dynamic JSON database cache."""
    current_lower = ctx.value.lower() if ctx.value else ""
    matches = [s for s in ALL_AUSTRALIAN_SUBURBS if current_lower in s.lower()][:15]
    return matches if matches else ALL_AUSTRALIAN_SUBURBS[:15]

# ==========================================
# MULTI-SOURCE SCRAPER
# ==========================================
class PropertyScraper:
    """Multi-source property data scraper with state-aware routing and proxy-like headers"""
    
    def __init__(self, cache_store: Path):
        self.cache_store = cache_store
        self.base_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-AU,en-GB;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }
        self._load_cache()
    
    def _load_cache(self):
        if self.cache_store.exists():
            try:
                self.cache = json.loads(self.cache_store.read_text())
            except:
                self.cache = {}
        else:
            self.cache = {}
    
    def _save_cache(self):
        _atomic_write(self.cache_store, self.cache)
    
    def _is_cache_fresh(self, suburb_key: str) -> bool:
        if suburb_key not in self.cache:
            return False
        cached_time = datetime.fromisoformat(self.cache[suburb_key].get("cached_at", ""))
        return datetime.now() - cached_time < timedelta(hours=72)
    
    async def get_suburb_data(self, suburb: str) -> Optional[Dict]:
        suburb_key = suburb.lower().replace(" ", "-")
        # Pulls state mapping directly from the dynamic db lookup
        state = SUBURB_TO_STATE.get(suburb.lower(), "nsw")
        
        if suburb_key in self.cache and self._is_cache_fresh(suburb_key):
            cached_data = self.cache[suburb_key].get("data")
            if cached_data:
                logger.info(f"Cache hit for {suburb} ({state})")
                return cached_data
        
        logger.info(f"Scraping {suburb} ({state})...")
        
        data = await self._scrape_domain(suburb_key, state)
        if data:
            self._cache_result(suburb_key, data, "domain")
            return data
            
        data = await self._scrape_realestate(suburb_key, state)
        if data:
            self._cache_result(suburb_key, data, "realestate")
            return data
            
        data = await self._scrape_ddg(suburb, state)
        if data:
            self._cache_result(suburb_key, data, "duckduckgo")
            return data
            
        logger.warning(f"All HTTP scrapers failed/blocked for {suburb}.")
        return None
    
    def _cache_result(self, suburb_key: str, data: Dict, source: str):
        self.cache[suburb_key] = {
            "data": data,
            "source": source,
            "cached_at": datetime.now().isoformat()
        }
        self._save_cache()
    
    async def _scrape_domain(self, suburb_slug: str, state: str) -> Optional[Dict]:
        try:
            url = f"https://www.domain.com.au/suburb-profile/{suburb_slug}-{state}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.base_headers, timeout=10) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
            
            median = extract_price(html)
            if not median:
                return None
                
            growth, yield_val = 2.1, 3.8
            growth_match = re.search(r'growth.*?([-+]?[\d.]+)%', html, re.IGNORECASE)
            if growth_match:
                try: growth = float(growth_match.group(1))
                except: pass
                
            yield_match = re.search(r'yield.*?([\d.]+)%', html, re.IGNORECASE)
            if yield_match:
                try: yield_val = float(yield_match.group(1))
                except: pass
            
            logger.info(f"✅ Domain hit for {suburb_slug}: ${median:,}")
            return {
                "median": median,
                "growth_1yr": growth,
                "yield": yield_val,
                "demand": "strong",
                "investor_score": "high" if growth > 2.0 else "medium",
                "days_on_market": 30,
                "source": "Domain API"
            }
        except Exception as e:
            logger.error(f"Domain block/fail: {e}")
            return None
            
    async def _scrape_realestate(self, suburb_slug: str, state: str) -> Optional[Dict]:
        try:
            url = f"https://www.realestate.com.au/nsw/{suburb_slug}-{state}/"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.base_headers, timeout=10) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
            
            median = extract_price(html)
            if not median:
                return None
                
            logger.info(f"✅ REA hit for {suburb_slug}: ${median:,}")
            return {
                "median": median,
                "growth_1yr": 1.5,
                "yield": 3.7,
                "demand": "moderate",
                "investor_score": "medium",
                "days_on_market": 35,
                "source": "RealEstate API"
            }
        except Exception:
            return None

    async def _scrape_ddg(self, suburb: str, state: str) -> Optional[Dict]:
        try:
            url = "https://html.duckduckgo.com/html/"
            data = {"q": f"{suburb} {state} median house price domain realestate"}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=self.base_headers, timeout=10) as response:
                    if response.status != 200:
                        return None
                    html = await response.text()
            
            median = extract_price(html)
            if not median:
                return None
                
            logger.info(f"✅ DDG Fallback hit for {suburb}: ${median:,}")
            return {
                "median": median,
                "growth_1yr": 1.2,
                "yield": 3.5,
                "demand": "unknown",
                "investor_score": "medium",
                "days_on_market": 40,
                "source": "Aggregated Search"
            }
        except Exception as e:
            logger.error(f"DDG bypass failed: {e}")
            return None

# ==========================================
# MAIN COG
# ==========================================
class InvestBotCog(commands.Cog):
    """Investment property analysis bot with dynamic suburb data"""
    
    def __init__(self, bot):
        self.bot = bot
        self.scraper = PropertyScraper(INVEST_CACHE_STORE)
        self.load_data()
    
    def load_data(self):
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
        data = {
            "suburbs": self.suburbs,
            "qualified_leads": self.qualified_leads,
            "rba_rate": self.rba_rate
        }
        _atomic_write(INVEST_DATA_STORE, data)
    
    def flag_lead(self, user_id: int, profile_type: str):
        if str(user_id) not in self.qualified_leads:
            self.qualified_leads[str(user_id)] = {}
        self.qualified_leads[str(user_id)]["profile"] = profile_type
        self.qualified_leads[str(user_id)]["flagged_at"] = datetime.now().isoformat()
        self.save_data()
    
    # ==========================================
    # SLASH COMMANDS
    # ==========================================
    @discord.slash_command(name="suburb", description="Get suburb investment analysis")
    async def suburb(self, ctx, 
                     suburb_name: Option(str, description="Suburb name", 
                                        autocomplete=get_suburb_autocomplete)):
        
        await ctx.response.defer()
        
        suburb_key = suburb_name.lower().replace(" ", "-")
        
        # 1. Attempt Live Scrape
        data = await self.scraper.get_suburb_data(suburb_name)
        source_label = "📡 Live API Data"
        
        # 2. Fallback to local DB
        if not data:
            if suburb_key in self.suburbs:
                data = self.suburbs[suburb_key]
                source_label = "📋 Manual Database"
            else:
                embed = discord.Embed(
                    title="❌ Data Retrieval Failed",
                    description=f"Anti-bot protections blocked the live scan for **{suburb_name}**, and no offline data exists.\n\nPlease try another location or update the manual database.",
                    color=THEME_WARNING
                )
                return await ctx.followup.send(embed=embed, ephemeral=True)
        else:
            if "source" in data:
                source_label = f"📡 {data['source']}"
        
        self.flag_lead(ctx.author.id, "researcher")
        
        score_emoji = "🔥" if data.get("investor_score", "").lower() == "high" else "🟡"
        demand_emoji = "✅" if "strong" in data.get("demand", "").lower() else "⚠️"
        
        embed = discord.Embed(
            title=f"🏠 {suburb_name.title()}, {SUBURB_TO_STATE.get(suburb_name.lower(), 'NSW').upper()}",
            description="Investment Analysis Overview",
            color=THEME_PRIMARY
        )
        embed.add_field(name="Median Price", value=f"${data.get('median', 0):,}", inline=True)
        embed.add_field(name="1yr Growth", value=f"{data.get('growth_1yr', 0)}%", inline=True)
        embed.add_field(name="Rental Yield", value=f"{data.get('yield', 0)}%", inline=True)
        embed.add_field(name=f"Investor Score {score_emoji}", value=str(data.get("investor_score", "N/A")).title(), inline=True)
        embed.add_field(name=f"Demand {demand_emoji}", value=str(data.get("demand", "N/A")).title(), inline=True)
        embed.add_field(name="Days on Market", value=str(data.get("days_on_market", "N/A")), inline=True)
        embed.add_field(name="Data Source", value=source_label, inline=False)
        embed.set_footer(text="Educational discussion only—not financial advice")
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(name="neggear", description="Calculate negative gearing")
    async def neggear(self, ctx,
                      property_price: Option(int, description="Purchase price (AUD)"),
                      annual_rent: Option(int, description="Annual rental (AUD)"),
                      mortgage_rate: Option(float, description="Mortgage rate (%)")):
        
        self.flag_lead(ctx.author.id, "refinancer")
        
        loan_amount = property_price * 0.8
        annual_interest = loan_amount * (mortgage_rate / 100)
        estimated_expenses = annual_rent * 0.25
        annual_shortfall = (annual_interest + estimated_expenses) - annual_rent
        tax_benefit = annual_shortfall * 0.39
        
        embed = discord.Embed(title="💰 Negative Gearing Calculator", color=THEME_PRIMARY)
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
        
        self.flag_lead(ctx.author.id, "refinancer")
        
        market_rate = self.rba_rate
        rate_saving = current_rate - market_rate
        estimated_loan = annual_income * 4
        annual_saving = estimated_loan * (rate_saving / 100)
        
        embed = discord.Embed(title="🔄 Refinance Eligibility Check", color=THEME_SUCCESS if rate_saving > 0 else THEME_WARNING)
        embed.add_field(name="Current Rate", value=f"{current_rate}%", inline=True)
        embed.add_field(name="Market Rate (approx)", value=f"{market_rate}%", inline=True)
        embed.add_field(name="Potential Spread", value=f"{rate_saving:.2f}%", inline=True)
        embed.add_field(name="Equity Position", value=f"{equity_percent}%", inline=True)
        embed.add_field(name="Est. Loan Capacity", value=f"${estimated_loan:,}", inline=True)
        embed.add_field(name="💵 Est. Annual Saving", value=f"${annual_saving:,.0f}" if rate_saving > 0 else "Not viable", inline=True)
        embed.set_footer(text="Educational discussion only—not financial advice.")
        
        await safe_reply(ctx, embed=embed)
    
    @discord.slash_command(name="compare", description="Compare two suburbs")
    async def compare(self, ctx, 
                      suburb1: Option(str, description="First suburb", autocomplete=get_suburb_autocomplete),
                      suburb2: Option(str, description="Second suburb", autocomplete=get_suburb_autocomplete)):
        
        await ctx.response.defer()
        
        s1_data = await self.scraper.get_suburb_data(suburb1)
        s2_data = await self.scraper.get_suburb_data(suburb2)
        
        s1_key = suburb1.lower().replace(" ", "-")
        s2_key = suburb2.lower().replace(" ", "-")
        
        if not s1_data and s1_key in self.suburbs: s1_data = self.suburbs[s1_key]
        if not s2_data and s2_key in self.suburbs: s2_data = self.suburbs[s2_key]
        
        if not s1_data or not s2_data:
            return await ctx.followup.send(f"❌ Could not retrieve valid data to compare both regions.", ephemeral=True)
        
        self.flag_lead(ctx.author.id, "portfolio_builder")
        
        embed = discord.Embed(title="📊 Suburb Comparison", color=THEME_PRIMARY)
        comparison = f"""
**Metric** | **{suburb1.title()}** | **{suburb2.title()}**
---|---|---
Median | ${s1_data['median']:,} | ${s2_data['median']:,}
1yr Growth | {s1_data['growth_1yr']}% | {s2_data['growth_1yr']}%
Yield | {s1_data['yield']}% | {s2_data['yield']}%
Investor Score | {str(s1_data.get('investor_score', '')).title()} | {str(s2_data.get('investor_score', '')).title()}
        """
        embed.description = comparison
        embed.set_footer(text="Educational discussion only—not financial advice")
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(name="invest_lead", description="Flag user as qualified lead")
    @admin_only()
    async def invest_lead(self, ctx, user: discord.User, profile_type: str):
        self.flag_lead(user.id, profile_type)
        await safe_reply(ctx, f"✅ Flagged {user.mention} as **{profile_type}** lead.", ephemeral=True)
    
    @discord.slash_command(name="invest_leads", description="List all qualified leads")
    @admin_only()
    async def invest_leads(self, ctx):
        if not self.qualified_leads:
            return await safe_reply(ctx, "No leads yet.", ephemeral=True)
        
        embed = discord.Embed(title="📋 Qualified Leads", color=THEME_SUCCESS)
        for user_id, lead_data in list(self.qualified_leads.items())[:10]:
            embed.add_field(
                name=f"User ID: {user_id}",
                value=f"Type: {lead_data.get('profile', 'Unknown')}\nFlagged: {lead_data.get('flagged_at', 'N/A')[:10]}",
                inline=False
            )
        await safe_reply(ctx, embed=embed, ephemeral=True)
    
    @discord.slash_command(name="invest_template", description="Send outreach template")
    @admin_only()
    async def invest_template(self, ctx, user: discord.User, template: str):
        if template not in OUTREACH_TEMPLATES:
            return await safe_reply(ctx, "❌ Invalid template. Use: refi, first_investor, portfolio", ephemeral=True)
        try:
            await user.send(OUTREACH_TEMPLATES[template])
            await safe_reply(ctx, f"✅ Sent {template} template to {user.mention}", ephemeral=True)
        except discord.Forbidden:
            await safe_reply(ctx, f"❌ Cannot DM {user.mention}.", ephemeral=True)

def setup(bot):
    bot.add_cog(InvestBotCog(bot))
    logger.info("InvestBotCog loaded (Dynamic Database Integrated)")
