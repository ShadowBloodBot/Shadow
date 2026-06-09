"""Optional live suburb enrichment — Domain profile when reachable, else census locality data."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger("ShadowSyn.SuburbFetcher")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
}


def _slug(name: str, state: str) -> str:
    return f"{name.lower().replace(' ', '-')}-{state.lower()}"


def census_to_stats(record: dict) -> dict:
    """Build discussion profile from ABS locality census row."""
    pop = int(record.get("population") or 0)
    income = int(record.get("median_income") or 0)
    sqkm = float(record.get("sqkm") or 0)
    density = round(pop / sqkm, 1) if sqkm > 0 and pop > 0 else None
    return {
        "name": record["name"],
        "state": record["state"],
        "postcode": record.get("postcode"),
        "population": pop,
        "median_income": income,
        "sqkm": sqkm,
        "density_per_sqkm": density,
        "lga": record.get("lga"),
        "urban_area": record.get("urban_area"),
        "median_price": None,
        "growth_12m_pct": None,
        "rental_yield_pct": None,
        "median_rent_weekly": None,
        "rental_demand_score": min(100, max(20, int(pop / 200))) if pop else 50,
        "source": "ABS 2016 locality census data (discussion model)",
        "profile_type": "census",
    }


def _parse_domain_next_data(html: str) -> dict[str, Any] | None:
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
        return data.get("props", {}).get("pageProps", {})
    except json.JSONDecodeError:
        return None


def _extract_domain_stats(page_props: dict) -> dict[str, Any] | None:
    """Best-effort parse — Domain page structure changes over time."""
    suburb_data = page_props.get("suburb") or page_props.get("suburbProfile") or page_props
    if not isinstance(suburb_data, dict):
        return None

    def dig(*keys, default=None):
        cur = suburb_data
        for k in keys:
            if not isinstance(cur, dict):
                return default
            cur = cur.get(k)
        return cur if cur is not None else default

    median = dig("medianSoldPrice") or dig("demographics", "medianSoldPrice")
    growth = dig("annualGrowth") or dig("priceGrowth", "annual")
    yield_pct = dig("rentalYield") or dig("demographics", "rentalYield")
    rent = dig("medianRent") or dig("demographics", "medianRent")

    if median is None and growth is None and yield_pct is None:
        return None

    return {
        "median_price": int(median) if median else None,
        "growth_12m_pct": float(growth) if growth is not None else None,
        "rental_yield_pct": float(yield_pct) if yield_pct is not None else None,
        "median_rent_weekly": int(rent) if rent else None,
        "source": "Domain suburb profile (indicative, discussion only)",
        "profile_type": "domain",
    }


async def fetch_domain_stats(name: str, state: str) -> dict[str, Any] | None:
    url = f"https://www.domain.com.au/suburb-profile/{_slug(name, state)}"
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=20, follow_redirects=True) as client:
            resp = await client.get(url)
        if resp.status_code != 200:
            logger.info(f"Domain fetch {url} -> HTTP {resp.status_code}")
            return None
        page_props = _parse_domain_next_data(resp.text)
        if not page_props:
            return None
        stats = _extract_domain_stats(page_props)
        if stats:
            stats["name"] = name
            stats["state"] = state.upper()
        return stats
    except Exception as e:
        logger.warning(f"Domain fetch failed for {name}: {e}")
        return None


async def build_suburb_profile(record: dict, *, try_domain: bool = True) -> dict:
    """Merge census locality data with optional Domain enrichment."""
    profile = census_to_stats(record)
    if not try_domain:
        return profile
    domain = await fetch_domain_stats(record["name"], record["state"])
    if domain:
        profile.update({k: v for k, v in domain.items() if v is not None})
        profile["profile_type"] = "domain+census"
        if profile.get("rental_demand_score") and profile.get("population"):
            profile["rental_demand_score"] = min(
                100, profile["rental_demand_score"] + 10
            )
    return profile
