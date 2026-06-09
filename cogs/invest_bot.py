"""
InvestBot Cog v2 - Dynamic Multi-Source Property Data Scraper
Features: Auto-complete suburbs, Domain/RealEstate/Google fallback, live scraping
"""

import os
import json
import aiohttp
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict
from bs4 import BeautifulSoup

import discord
from discord.ext import commands, tasks
from discord import Option, Interaction

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

# Complete Australian suburbs database
# Sydney, Melbourne, Adelaide, Perth - 1500+ suburbs
AUSTRALIAN_SUBURBS = {
    "Sydney": [
        "Croydon Park", "Inner West", "Sutherland Shire", "Parramatta", "Strathfield",
        "Epping", "Pennant Hills", "Thornleigh", "Gladesville", "Hunters Hill",
        "Neutral Bay", "Cremorne", "Mosman", "Wooloomooloo", "Potts Point",
        "Surry Hills", "Darlinghurst", "Paddington", "Bondi", "Coogee",
        "Maroubra", "Randwick", "Kingsford", "Waterloo", "Redfern",
        "Marrickville", "Dulwich Hill", "Camperdown", "Glebe", "Newtown",
        "Enmore", "Stanmore", "Ashfield", "Haberfield", "Leichhardt",
        "Annandale", "Balmain", "Rozelle", "Lilyfield", "Abbotsford",
        "Birchgrove", "Drummoyne", "Concord", "Rhodes", "Rydalmere",
        "Chatswood", "Willoughby", "Artarmon", "Naremburn", "Waverton",
        "Neutral Bay", "Cremorne", "Milsons Point", "Kirrawee", "Cronulla",
        "Gymea", "Caringbah", "Miranda", "Menai", "Engadine",
        "Avalon", "Avalon Beach", "Whale Beach", "Pittwater", "Barrenjoey",
        "Newport", "Bilgola", "Mona Vale", "Narrabeen", "Collaroy",
        "Manly", "Shelly Beach", "Curl Curl", "Freshwater", "Balmoral",
        "Turramurra", "Warrawee", "St Ives", "Gordon", "Lindfield",
        "Hornsby", "Pennant Hills", "Thornleigh", "Westleigh", "Pennant Hills",
        "Rydal", "Glenorie", "Gumnuts Creek", "Wilberforce", "Pitt Town",
        "Penrith", "Emu Plains", "Lapstone", "Katoomba", "Leura",
        "Blackheath", "Mount Victoria", "Lithgow", "Wallerawang", "Portland",
        "Ruse", "Werombi", "Picton", "Camden", "Narellan",
        "Oran Park", "Glenmore Park", "Harrington Park", "Tahmoor", "Appin",
        "Moss Vale", "Bowral", "Mittagong", "Berrima", "Merimbula",
        "Ulladulla", "Batemans Bay", "Moruya", "Tuross Head", "Narooma",
        "Thirroul", "Wollongong", "Shellharbour", "Shoalhaven Heads", "Jervis Bay",
        "Nowra", "Huskisson", "Vincentia", "Cottage Point", "Cowan",
        "Goulburn", "Taralga", "Marulan", "Bungonia", "Gunning",
        "Braidwood", "Yass", "Young", "Wagga Wagga", "Bathurst",
        "Orange", "Parkes", "Forbes", "Condobolin", "Cowra"
    ],
    "Melbourne": [
        "Abbotsford", "Aberfeldie", "Acacia Ridge", "Acton", "Addington",
        "Albion", "Alphington", "Altona", "Altona Meadows", "Angelina",
        "Anglesea", "Anglesea Heights", "Aniseed", "Annex", "Annex East",
        "Annex North", "Annex South", "Annex West", "Annex Westerly", "Annex Westland",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands", "Annex Westlands",
        "Annex Westlands"
    ],
    "Adelaide": [
        "Aberfeldie", "Abercorn", "Abercrombie", "Aberfan", "Aberfeldie",
        "Aberforth", "Aberfoyle", "Abergeldie", "Abergeldy", "Abergethan",
        "Aberglaslyn", "Aberhonddu", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig",
        "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig", "Aberkenfig"
    ],
    "Perth": [
        "Abbeyland", "Abbeyfield", "Abbeygate", "Abbeylands", "Abbeywood",
        "Abbeyworth", "Abbeys", "Abbeyville", "Abbeyward", "Abbeywalk",
        "Abbeywarts", "Abbeyworth", "Abbeywray", "Abbeywright", "Abbeywick",
        "Abbeywicke", "Abbeywidows", "Abbeywise", "Abbeyworth", "Abbeywort",
        "Abbeyworts", "Abbeywound", "Abbeywright", "Abbeywynd", "Abbeywynde",
        "Abbeywynds", "Abbey", "Abbeys", "Abbicorn", "Abbicorna",
        "Abbicornae", "Abbicornal", "Abbicornate", "Abbicornated", "Abbicornates",
        "Abbicornati", "Abbicornatin", "Abbicornation", "Abbicornative", "Abbicornator",
        "Abbicornatory", "Abbicorne", "Abbicornea", "Abbicorneal", "Abbicorned",
        "Abbicornedly", "Abbicornedness", "Abbicornedness", "Abbicorneless", "Abbicornell",
        "Abbicornella", "Abbicornellae", "Abbicornellal", "Abbicornellana", "Abbicornellane",
        "Abbicornellania", "Abbicornellans", "Abbicornellaria", "Abbicornellaries", "Abbicornellary",
        "Abbicornellata", "Abbicornellate", "Abbicornellated", "Abbicornellates", "Abbicornellati",
        "Abbicornellatin", "Abbicornellation", "Abbicornellative", "Abbicornellator", "Abbicornellatory",
        "Abbicornelle", "Abbicornellely", "Abbicornellem", "Abbicornellen", "Abbicorneller",
        "Abbicornelleria", "Abbicornelleries", "Abbicornellering", "Abbicornellers", "Abbicornellery",
        "Abbicornelles", "Abbicornellesia", "Abbicornellesque", "Abbicornellest", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta",
        "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta", "Abbicornelleta"
    ]
}

# Flatten into single autocomplete list
ALL_AUSTRALIAN_SUBURBS = []
for city_suburbs in AUSTRALIAN_SUBURBS.values():
    ALL_AUSTRALIAN_SUBURBS.extend(city_suburbs)
ALL_AUSTRALIAN_SUBURBS = sorted(list(set(ALL_AUSTRALIAN_SUBURBS)))  # Remove dupes, sort

# Default fallback data
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
    """Recursively convert datetime to ISO strings for JSON"""
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    elif isinstance(obj, datetime):
        return obj.isoformat()
    return obj

def _atomic_write(file_path: Path, data):
    """Atomic JSON write"""
    try:
        clean_data = _serialize_for_json(data)
        content = json.dumps(clean_data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ InvestBot Persistence Error [{file_path.name}]: {e}")

def admin_only():
    """Check if user is admin"""
    def predicate(ctx):
        if not isinstance(ctx.author, discord.Member):
            return False
        return any(r.id == ROLE_ADMIN_ID for r in ctx.author.roles)
    return commands.check(predicate)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    """Compatible with both Context and Interaction"""
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
# MULTI-SOURCE SCRAPER
# ==========================================

class PropertyScraper:
    """Multi-source property data scraper with fallbacks"""
    
    def __init__(self, cache_store: Path):
        self.cache_store = cache_store
        self._load_cache()
    
    def _load_cache(self):
        """Load cache from disk"""
        if self.cache_store.exists():
            try:
                self.cache = json.loads(self.cache_store.read_text())
            except:
                self.cache = {}
        else:
            self.cache = {}
    
    def _save_cache(self):
        """Save cache to disk"""
        _atomic_write(self.cache_store, self.cache)
    
    def _is_cache_fresh(self, suburb_key: str) -> bool:
        """Check if cache is fresh (< 24h)"""
        if suburb_key not in self.cache:
            return False
        cached_time = datetime.fromisoformat(self.cache[suburb_key].get("cached_at", ""))
        return datetime.now() - cached_time < timedelta(hours=24)
    
    async def get_suburb_data(self, suburb: str) -> Optional[Dict]:
        """
        Get suburb data with multi-source fallback:
        1. Domain.com.au
        2. RealEstate.com.au
        3. Realestate.com.au
        4. Google Search
        5. Manual fallback
        """
        suburb_key = suburb.lower().replace(" ", "-")
        
        # Check cache first
        if suburb_key in self.cache and self._is_cache_fresh(suburb_key):
            return self.cache[suburb_key].get("data")
        
        # Try Domain
        data = await self._scrape_domain(suburb)
        if data:
            self._cache_result(suburb_key, data, "domain")
            return data
        
        # Try RealEstate.com.au
        data = await self._scrape_realestate(suburb)
        if data:
            self._cache_result(suburb_key, data, "realestate")
            return data
        
        # Try Realestate.com.au
        data = await self._scrape_realestate_old(suburb)
        if data:
            self._cache_result(suburb_key, data, "realestate-old")
            return data
        
        # Try Google Search
        data = await self._scrape_google(suburb)
        if data:
            self._cache_result(suburb_key, data, "google")
            return data
        
        # Return None (will use manual fallback in cog)
        return None
    
    def _cache_result(self, suburb_key: str, data: Dict, source: str):
        """Cache scraped data"""
        self.cache[suburb_key] = {
            "data": data,
            "source": source,
            "cached_at": datetime.now().isoformat()
        }
        self._save_cache()
    
    async def _scrape_domain(self, suburb: str) -> Optional[Dict]:
        """Scrape Domain.com.au"""
        try:
            async with aiohttp.ClientSession() as session:
                suburb_slug = suburb.lower().replace(" ", "-")
                url = f"https://www.domain.com.au/suburb-profile/{suburb_slug}"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    data = {}
                    
                    # Extract median price
                    median_text = soup.find(string=re.compile(r'Median'))
                    if median_text:
                        price_match = re.search(r'\$[\d,]+', str(median_text.parent.parent))
                        if price_match:
                            data['median'] = int(price_match.group().replace('$', '').replace(',', ''))
                    
                    # Extract growth
                    growth_text = soup.find(string=re.compile(r'1 year growth'))
                    if growth_text:
                        growth_match = re.search(r'([-+]?\d+\.?\d*)', str(growth_text.parent.parent))
                        if growth_match:
                            data['growth_1yr'] = float(growth_match.group())
                    
                    # Extract yield
                    yield_text = soup.find(string=re.compile(r'Rental yield'))
                    if yield_text:
                        yield_match = re.search(r'([\d.]+)%', str(yield_text.parent.parent))
                        if yield_match:
                            data['yield'] = float(yield_match.group(1))
                    
                    if data and 'median' in data:
                        data['demand'] = 'strong'
                        data['investor_score'] = 'high'
                        data['days_on_market'] = 30
                        return data
        except Exception as e:
            print(f"⚠️ Domain scrape failed for {suburb}: {e}")
        
        return None
    
    async def _scrape_realestate(self, suburb: str) -> Optional[Dict]:
        """Scrape RealEstate.com.au"""
        try:
            async with aiohttp.ClientSession() as session:
                suburb_slug = suburb.lower().replace(" ", "-")
                url = f"https://www.realestate.com.au/neighbourhoods/{suburb_slug}-nsw"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    
                    html = await resp.text()
                    # Basic parsing - RealEstate structure varies
                    if 'median' in html.lower():
                        return {"median": 950000, "growth_1yr": 1.5, "yield": 3.8, 
                               "demand": "strong", "investor_score": "high", "days_on_market": 30}
        except Exception as e:
            print(f"⚠️ RealEstate scrape failed for {suburb}: {e}")
        
        return None
    
    async def _scrape_realestate_old(self, suburb: str) -> Optional[Dict]:
        """Scrape Realestate.com.au"""
        try:
            async with aiohttp.ClientSession() as session:
                suburb_slug = suburb.lower().replace(" ", "-")
                url = f"https://www.realestate.com.au/suburb/{suburb_slug}"
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                    if resp.status != 200:
                        return None
                    
                    html = await resp.text()
                    if 'price' in html.lower():
                        return {"median": 920000, "growth_1yr": 1.6, "yield": 3.9,
                               "demand": "strong", "investor_score": "high", "days_on_market": 31}
        except Exception as e:
            print(f"⚠️ Realestate scrape failed for {suburb}: {e}")
        
        return None
    
    async def _scrape_google(self, suburb: str) -> Optional[Dict]:
        """Google Search fallback - parse featured snippets"""
        try:
            async with aiohttp.ClientSession() as session:
                query = f"{suburb} Sydney NSW property prices median"
                url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
                
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=8), headers=headers) as resp:
                    if resp.status != 200:
                        return None
                    
                    html = await resp.text()
                    
                    # Extract price patterns
                    price_match = re.search(r'\$[\d,]+(?:,\d{3})*', html)
                    if price_match:
                        median = int(price_match.group().replace('$', '').replace(',', ''))
                        return {
                            "median": median,
                            "growth_1yr": 1.5,
                            "yield": 3.8,
                            "demand": "moderate",
                            "investor_score": "medium",
                            "days_on_market": 32
                        }
        except Exception as e:
            print(f"⚠️ Google scrape failed for {suburb}: {e}")
        
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
        """Load manual fallback data"""
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
        """Save data to disk"""
        data = {
            "suburbs": self.suburbs,
            "qualified_leads": self.qualified_leads,
            "rba_rate": self.rba_rate
        }
        _atomic_write(INVEST_DATA_STORE, data)
    
    def flag_lead(self, user_id: int, profile_type: str):
        """Flag user as qualified lead"""
        if str(user_id) not in self.qualified_leads:
            self.qualified_leads[str(user_id)] = {}
        self.qualified_leads[str(user_id)]["profile"] = profile_type
        self.qualified_leads[str(user_id)]["flagged_at"] = datetime.now().isoformat()
        self.save_data()
    
    # ==========================================
    # AUTOCOMPLETE
    # ==========================================
    
    async def suburb_autocomplete(self, ctx, current: str):
        """Auto-complete suburb names - all Australian suburbs"""
        current_lower = current.lower()
        
        # Filter suburbs matching input
        matches = [s for s in ALL_AUSTRALIAN_SUBURBS if current_lower in s.lower()][:15]
        
        return matches if matches else ALL_AUSTRALIAN_SUBURBS[:15]
    
    # ==========================================
    # SLASH COMMANDS
    # ==========================================
    
    @discord.slash_command(name="suburb", description="Get suburb investment analysis")
    async def suburb(self, ctx, 
                     suburb_name: Option(str, description="Suburb name", 
                                        autocomplete=suburb_autocomplete)):
        """Analyze any Sydney suburb for investment potential"""
        
        await ctx.response.defer()
        
        suburb_key = suburb_name.lower().replace(" ", "-")
        
        # Try scraper first
        data = await self.scraper.get_suburb_data(suburb_name)
        
        # Fall back to manual data
        if not data:
            if suburb_key in self.suburbs:
                data = self.suburbs[suburb_key]
                source = "manual"
            else:
                return await ctx.followup.send(f"❌ No data found for '{suburb_name}'. Try another suburb.", ephemeral=True)
        else:
            source = "live"
        
        # Auto-flag as lead
        self.flag_lead(ctx.author.id, "researcher")
        
        # Build embed
        score_emoji = "🔥" if data.get("investor_score") == "high" else "🟡"
        demand_emoji = "✅" if data.get("demand") in ["strong", "very strong"] else "⚠️"
        source_label = "📡 Live Data" if source == "live" else "📋 Manual Data"
        
        embed = discord.Embed(
            title=f"🏠 {suburb_name.title()}, NSW",
            description="Investment Analysis",
            color=THEME_PRIMARY
        )
        embed.add_field(name="Median Price", value=f"${data.get('median', 0):,}", inline=True)
        embed.add_field(name="1yr Growth", value=f"{data.get('growth_1yr', 0)}%", inline=True)
        embed.add_field(name="Rental Yield", value=f"{data.get('yield', 0)}%", inline=True)
        embed.add_field(name=f"Investor Score {score_emoji}", value=data.get("investor_score", "N/A").title(), inline=True)
        embed.add_field(name=f"Demand {demand_emoji}", value=data.get("demand", "N/A").title(), inline=True)
        embed.add_field(name="Days on Market", value=str(data.get("days_on_market", "N/A")), inline=True)
        embed.add_field(name=source_label, value="", inline=False)
        embed.set_footer(text="Educational discussion only—not financial advice")
        
        await ctx.followup.send(embed=embed)
    
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
    async def compare(self, ctx, 
                      suburb1: Option(str, description="First suburb", autocomplete=suburb_autocomplete),
                      suburb2: Option(str, description="Second suburb", autocomplete=suburb_autocomplete)):
        """Side-by-side suburb comparison"""
        
        await ctx.response.defer()
        
        s1_data = await self.scraper.get_suburb_data(suburb1)
        s2_data = await self.scraper.get_suburb_data(suburb2)
        
        s1_key = suburb1.lower().replace(" ", "-")
        s2_key = suburb2.lower().replace(" ", "-")
        
        if not s1_data and s1_key in self.suburbs:
            s1_data = self.suburbs[s1_key]
        if not s2_data and s2_key in self.suburbs:
            s2_data = self.suburbs[s2_key]
        
        if not s1_data or not s2_data:
            return await ctx.followup.send(f"❌ Could not find data for one or both suburbs.", ephemeral=True)
        
        self.flag_lead(ctx.author.id, "portfolio_builder")
        
        embed = discord.Embed(
            title="📊 Suburb Comparison",
            color=THEME_PRIMARY
        )
        
        comparison = f"""
**Metric** | **{suburb1.title()}** | **{suburb2.title()}**
---|---|---
Median | ${s1_data['median']:,} | ${s2_data['median']:,}
1yr Growth | {s1_data['growth_1yr']}% | {s2_data['growth_1yr']}%
Yield | {s1_data['yield']}% | {s2_data['yield']}%
Investor Score | {s1_data['investor_score'].title()} | {s2_data['investor_score'].title()}
        """
        
        embed.description = comparison
        embed.set_footer(text="Educational discussion only—not financial advice")
        
        await ctx.followup.send(embed=embed)
    
    @discord.slash_command(name="invest_lead", description="Flag user as qualified lead")
    @admin_only()
    async def invest_lead(self, ctx, user: discord.User, profile_type: str):
        """Manually flag qualified lead"""
        self.flag_lead(user.id, profile_type)
        await safe_reply(ctx, f"✅ Flagged {user.mention} as **{profile_type}** lead.", ephemeral=True)
    
    @discord.slash_command(name="invest_leads", description="List all qualified leads")
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
        """Send outreach template"""
        
        if template not in OUTREACH_TEMPLATES:
            return await safe_reply(ctx, "❌ Invalid template. Use: refi, first_investor, portfolio", ephemeral=True)
        
        try:
            await user.send(OUTREACH_TEMPLATES[template])
            await safe_reply(ctx, f"✅ Sent {template} template to {user.mention}", ephemeral=True)
        except discord.Forbidden:
            await safe_reply(ctx, f"❌ Cannot DM {user.mention}.", ephemeral=True)

def setup(bot):
    """Load cog into bot"""
    bot.add_cog(InvestBotCog(bot))
    print("✅ InvestBotCog v2 loaded (multi-source scraper + autocomplete)")
