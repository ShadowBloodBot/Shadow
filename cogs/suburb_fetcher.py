"""Suburb profile builder — Domain API for price/rent, census for context."""

from __future__ import annotations

import logging
from pathlib import Path

from cogs.domain_api import get_domain_api

logger = logging.getLogger("ShadowSyn.SuburbFetcher")


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


async def build_suburb_profile(record: dict, *, persist: Path | None = None) -> dict:
    profile = census_to_stats(record)
    api = get_domain_api(persist)

    if not api.configured:
        profile["price_note"] = (
            "Median price/rent unavailable — set DOMAIN_CLIENT_ID and DOMAIN_CLIENT_SECRET on Railway."
        )
        return profile

    domain = await api.fetch_house_stats(
        record["state"],
        record["name"],
        record.get("postcode") or "",
    )
    if domain:
        profile.update({k: v for k, v in domain.items() if v is not None})
        profile["profile_type"] = "domain_api+census"
        profile.pop("price_note", None)
    else:
        profile["price_note"] = (
            "Domain API returned no house median for this locality — check spelling/postcode or try Domain link."
        )

    return profile
