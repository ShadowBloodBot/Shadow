"""Domain.com.au API client — suburb median price and rent (requires API credentials)."""

from __future__ import annotations

import base64
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("ShadowSyn.DomainAPI")

AUTH_URL = "https://auth.domain.com.au/v1/connect/token"
API_BASE = "https://api.domain.com.au/v2/suburbPerformanceStatistics"
CACHE_TTL_SEC = 7 * 24 * 3600


class DomainAPI:
    def __init__(self, persist: Path | None = None):
        self.client_id = os.getenv("DOMAIN_CLIENT_ID", "").strip()
        self.client_secret = os.getenv("DOMAIN_CLIENT_SECRET", "").strip()
        self.api_key = os.getenv("DOMAIN_API_KEY", "").strip()
        self.persist = persist or Path(os.getenv("PERSIST_PATH", "/data"))
        self._token: str | None = None
        self._token_exp: float = 0
        self._cache_path = self.persist / "domain_suburb_cache.json"
        self._cache: dict[str, dict] = self._load_cache()

    @property
    def configured(self) -> bool:
        return bool(self.api_key or (self.client_id and self.client_secret))

    def _load_cache(self) -> dict:
        if not self._cache_path.exists():
            return {}
        try:
            with open(self._cache_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_cache(self):
        self.persist.mkdir(parents=True, exist_ok=True)
        tmp = self._cache_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._cache, f)
        tmp.replace(self._cache_path)

    def _cache_key(self, state: str, suburb: str, postcode: int | str) -> str:
        return f"{state.upper()}:{suburb.lower()}:{postcode}"

    def _get_cached(self, key: str) -> dict | None:
        entry = self._cache.get(key)
        if not entry:
            return None
        if time.time() - entry.get("fetched_at", 0) > CACHE_TTL_SEC:
            return None
        return entry.get("data")

    def _set_cached(self, key: str, data: dict):
        self._cache[key] = {"fetched_at": time.time(), "data": data}
        if len(self._cache) > 5000:
            oldest = sorted(self._cache, key=lambda k: self._cache[k]["fetched_at"])[:1000]
            for k in oldest:
                del self._cache[k]
        self._save_cache()

    async def _auth_headers(self) -> dict[str, str]:
        if self.api_key:
            return {"X-Api-Key": self.api_key}
        if not self.client_id or not self.client_secret:
            raise RuntimeError("Domain API not configured")
        if self._token and time.time() < self._token_exp - 60:
            return {"Authorization": f"Bearer {self._token}"}

        # https://developer.domain.com.au/docs/v2/authentication/oauth/client-credentials-grant
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                AUTH_URL,
                headers={
                    "Authorization": f"Basic {basic}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data={
                    "grant_type": "client_credentials",
                    "scope": "api_suburbperformance_read",
                },
            )
        if resp.status_code >= 400:
            logger.error(f"Domain OAuth failed: {resp.status_code} {resp.text[:300]}")
        resp.raise_for_status()
        payload = resp.json()
        self._token = payload["access_token"]
        self._token_exp = time.time() + int(payload.get("expires_in", 3600))
        return {"Authorization": f"Bearer {self._token}"}

    def _latest_values(self, series_info: list[dict]) -> dict[str, Any]:
        """Pick newest month with median sold price; newest with rent."""
        sold = None
        rent = None
        sorted_series = sorted(
            series_info,
            key=lambda x: (x.get("year", 0), x.get("month", 0)),
            reverse=True,
        )
        for point in sorted_series:
            vals = point.get("values") or {}
            if sold is None and vals.get("medianSoldPrice"):
                sold = {"price": int(vals["medianSoldPrice"]), "year": point["year"], "month": point["month"]}
            if rent is None and vals.get("medianRentListingPrice"):
                rent = {"rent": int(vals["medianRentListingPrice"]), "year": point["year"], "month": point["month"]}
            if sold and rent:
                break

        growth = None
        if len(sorted_series) >= 2:
            recent = next((p for p in sorted_series if (p.get("values") or {}).get("medianSoldPrice")), None)
            older = next(
                (p for p in reversed(sorted_series) if (p.get("values") or {}).get("medianSoldPrice")),
                None,
            )
            if recent and older and recent is not older:
                r = recent["values"]["medianSoldPrice"]
                o = older["values"]["medianSoldPrice"]
                if o:
                    growth = round(((r - o) / o) * 100, 1)

        return {"sold": sold, "rent": rent, "growth_12m_pct": growth}

    async def fetch_house_stats(self, state: str, suburb: str, postcode: int | str) -> dict | None:
        if not self.configured:
            return None

        key = self._cache_key(state, suburb, postcode)
        cached = self._get_cached(key)
        if cached:
            return cached

        url = f"{API_BASE}/{state.upper()}/{suburb}/{postcode}"
        params = {
            "propertyCategory": "House",
            "periodSize": "Months",
            "startingPeriodRelativeToCurrent": 1,
            "totalPeriods": 12,
        }

        try:
            headers = await self._auth_headers()
            async with httpx.AsyncClient(timeout=25) as client:
                resp = await client.get(url, headers=headers, params=params)
                if resp.status_code == 404:
                    logger.info(f"Domain API: no house stats for {suburb} {state} {postcode}")
                    url_no_pc = f"{API_BASE}/{state.upper()}/{suburb}"
                    resp = await client.get(url_no_pc, headers=headers, params=params)
            if resp.status_code == 404:
                logger.info(f"Domain API: no house stats for {suburb} {state}")
                return None
            if resp.status_code == 429:
                logger.warning("Domain API rate limit hit")
                return None
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning(f"Domain API error for {suburb}: {e}")
            return None

        series = (data.get("series") or {}).get("seriesInfo") or []
        parsed = self._latest_values(series)
        if not parsed["sold"] and not parsed["rent"]:
            return None

        result = {
            "median_price": parsed["sold"]["price"] if parsed["sold"] else None,
            "median_rent_weekly": parsed["rent"]["rent"] if parsed["rent"] else None,
            "growth_12m_pct": parsed["growth_12m_pct"],
            "rental_yield_pct": None,
            "source": "Domain suburb performance API (House, indicative)",
            "profile_type": "domain_api",
        }
        if result["median_price"] and result["median_rent_weekly"]:
            result["rental_yield_pct"] = round(
                (result["median_rent_weekly"] * 52 / result["median_price"]) * 100, 2
            )

        self._set_cached(key, result)
        return result


_api: DomainAPI | None = None


def get_domain_api(persist: Path | None = None) -> DomainAPI:
    global _api
    if _api is None:
        _api = DomainAPI(persist)
    return _api
