"""Suburb profile builder — Domain API for price/rent, census for context."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import httpx

from cogs.domain_api import get_domain_api

logger = logging.getLogger("ShadowSyn.SuburbFetcher")

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-AU,en;q=0.9",
    "Referer": "https://www.domain.com.au/",
}


def census_to_stats(record: dict) -> dict:
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


def _slug(name: str, state: str, postcode: int | str | None = None) -> str:
    base = f"{name.lower().replace(' ', '-')}-{state.lower()}"
    return f"{base}-{postcode}" if postcode else base


def _parse_domain_next_data(html: str) -> dict[str, Any] | None:
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html)
    if not m:
        return None
    try:
        return json.loads(m.group(1)).get("props", {}).get("pageProps", {})
    except json.JSONDecodeError:
        return None


def _extract_domain_page_stats(page_props: dict) -> dict[str, Any] | None:
    blob = json.dumps(page_props)
    out: dict[str, Any] = {}
    for key, pattern in {
        "median_price": r'"medianSoldPrice"\s*:\s*(\d+)',
        "median_rent_weekly": r'"medianRent(?:ListingPrice)?"\s*:\s*(\d+)',
        "growth_12m_pct": r'"annualGrowth"\s*:\s*(-?\d+\.?\d*)',
        "rental_yield_pct": r'"rentalYield"\s*:\s*(\d+\.?\d*)',
    }.items():
        m = re.search(pattern, blob)
        if m:
            out[key] = float(m.group(1)) if "." in m.group(1) or key.endswith("_pct") else int(m.group(1))
    if not out.get("median_price") and not out.get("median_rent_weekly"):
        return None
    out["source"] = "Domain suburb profile (indicative, discussion only)"
    out["profile_type"] = "domain_scrape"
    if out.get("median_price") and out.get("median_rent_weekly") and not out.get("rental_yield_pct"):
        out["rental_yield_pct"] = round((out["median_rent_weekly"] * 52 / out["median_price"]) * 100, 2)
    return out


async def _fetch_domain_page_stats(name: str, state: str, postcode: int | str | None) -> dict[str, Any] | None:
    for slug in filter(None, [_slug(name, state, postcode), _slug(name, state, None)]):
        url = f"https://www.domain.com.au/suburb-profile/{slug}"
        try:
            async with httpx.AsyncClient(headers=_HEADERS, timeout=20, follow_redirects=True) as client:
                resp = await client.get(url)
            if resp.status_code != 200:
                continue
            page_props = _parse_domain_next_data(resp.text)
            if page_props and (stats := _extract_domain_page_stats(page_props)):
                stats["name"] = name
                stats["state"] = state.upper()
                return stats
        except Exception as e:
            logger.debug(f"Domain page fetch failed for {slug}: {e}")
    return None


async def build_suburb_profile(record: dict, *, persist: Path | None = None) -> dict:
    profile = census_to_stats(record)
    api = get_domain_api(persist)
    domain: dict | None = None

    if api.configured:
        domain = await api.fetch_house_stats(
            record["state"],
            record["name"],
            record.get("postcode") or "",
        )

    if not domain:
        domain = await _fetch_domain_page_stats(
            record["name"], record["state"], record.get("postcode")
        )

    if domain:
        profile.update({k: v for k, v in domain.items() if v is not None})
        profile["profile_type"] = (
            "domain_api+census" if api.configured and domain.get("profile_type") == "domain_api" else "domain+census"
        )
    elif not api.configured:
        profile["price_note"] = (
            "Add **DOMAIN_CLIENT_ID** and **DOMAIN_CLIENT_SECRET** in Railway variables "
            "for median house price and rent on all suburbs."
        )
    else:
        profile["price_note"] = (
            "Domain returned no house median for this locality — try the Domain link below."
        )

    return profile
