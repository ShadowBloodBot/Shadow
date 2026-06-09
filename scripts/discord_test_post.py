import json
import asyncio
import random
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cogs.invest_data import PROPERTIES, STRATEGIES, DISCLAIMER, strategy_embed_parts

MCP = json.load(open(ROOT / ".cursor" / "mcp.json", encoding="utf-8"))
TOKEN = MCP["mcpServers"]["discord-admin"]["env"]["DISCORD_TOKEN"]
MARKET_CH = "1513361536469700638"
STRATEGIES_CH = "1513361590882402407"


def market_embed(prop: dict, test: bool = True) -> dict:
    rental = prop["type"] == "rental"
    tag = "Rental ROI Pick" if rental else "Growth Pick"
    suffix = " (Connection Test)" if test else ""
    fields = [
        {"name": "Suburb", "value": f"{prop['suburb']}, {prop['state']}", "inline": True},
        {"name": "Type", "value": f"{prop['beds']}br {prop['ptype']}", "inline": True},
        {"name": "Guide Price", "value": f"${prop['price']:,}", "inline": True},
    ]
    if rental:
        fields += [
            {"name": "Indicative Rent", "value": f"${prop['rent_wk']}/wk", "inline": True},
            {"name": "Gross Yield", "value": f"{prop['yield']}%", "inline": True},
        ]
    else:
        fields.append({"name": "5yr Growth (indicative)", "value": f"{prop['growth_5y']}% p.a.", "inline": True})
    slug = prop["suburb"].lower().replace(" ", "-")
    fields.append({
        "name": "Research",
        "value": f"[Domain listings](https://www.domain.com.au/sale/{slug}-{prop['state'].lower()})",
        "inline": False,
    })
    return {
        "embeds": [{
            "title": f"{'📈' if rental else '🚀'} Market Daily — {tag}{suffix}",
            "description": prop["hook"],
            "color": 0x43B581 if rental else 0x3498DB,
            "fields": fields,
            "footer": {"text": DISCLAIMER},
        }]
    }


def strategy_embed(item: dict, test: bool = True) -> dict:
    suffix = " (Connection Test)" if test else ""
    parts = strategy_embed_parts(item)
    fields = [{"name": name, "value": value, "inline": False} for name, value in parts["fields"]]
    return {
        "embeds": [{
            "title": f"{parts['title']}{suffix}",
            "description": parts["description"],
            "color": 0x2B0B35,
            "fields": fields,
            "footer": {"text": DISCLAIMER},
        }]
    }


async def send(session: aiohttp.ClientSession, channel_id: str, payload: dict) -> int:
    url = f"https://discord.com/api/v10/channels/{channel_id}/messages"
    headers = {"Authorization": f"Bot {TOKEN}", "Content-Type": "application/json"}
    async with session.post(url, headers=headers, json=payload) as resp:
        text = await resp.text()
        print(f"channel={channel_id} status={resp.status}")
        if resp.status >= 400:
            print(text[:500])
        return resp.status


async def main():
    rental = random.choice([p for p in PROPERTIES if p["type"] == "rental"])
    growth = random.choice([p for p in PROPERTIES if p["type"] == "growth"])
    strat = STRATEGIES[0]
    async with aiohttp.ClientSession() as session:
        await send(session, MARKET_CH, {"content": "✅ **ShadowAdmin connection test** — Market Daily feed."})
        await send(session, MARKET_CH, market_embed(rental))
        await send(session, MARKET_CH, market_embed(growth))
        await send(session, STRATEGIES_CH, {"content": "✅ **ShadowAdmin connection test** — Daily Strategy feed."})
        await send(session, STRATEGIES_CH, strategy_embed(strat))


if __name__ == "__main__":
    asyncio.run(main())
