"""Suburb market stats for invest_bot — bundled seed + optional persist override."""

import json
import logging
from pathlib import Path

logger = logging.getLogger("ShadowSyn.InvestSuburbStats")

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SEED_PATH = _REPO_ROOT / "data" / "suburb_stats.json"


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {path}: {e}")
        return {}


class SuburbStatsStore:
    def __init__(self, persist_path: Path | None = None):
        self._stats: dict[str, dict] = {}
        self._reload(persist_path)

    def _reload(self, persist_path: Path | None = None):
        merged = _load_json(_SEED_PATH)
        if persist_path:
            override = persist_path / "suburb_stats.json"
            merged.update(_load_json(override))
        self._stats = {k.lower().strip(): v for k, v in merged.items()}
        logger.info(f"Loaded {len(self._stats)} suburb stat records")

    def lookup(self, name: str) -> dict | None:
        key = name.lower().strip()
        if key in self._stats:
            return self._stats[key]
        for k, v in self._stats.items():
            if v.get("name", "").lower() == key:
                return v
        return None

    def all_names(self) -> list[str]:
        return sorted({v.get("name", k.title()) for k, v in self._stats.items()})

    def iter_stats(self) -> list[tuple[str, dict]]:
        return list(self._stats.items())

    def cache_stats(self, stats: dict, persist_path: Path | None = None):
        key = stats.get("name", "").lower().strip()
        if not key:
            return
        self._stats[key] = stats
        if persist_path:
            out = persist_path / "suburb_stats.json"
            persist_path.mkdir(parents=True, exist_ok=True)
            merged = _load_json(out)
            merged.update({k: v for k, v in self._stats.items()})
            tmp = out.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
            tmp.replace(out)

    def hotspot_score(self, stats: dict) -> int:
        """0–100 investor hotspot score from yield, growth, and demand."""
        yield_val = stats.get("rental_yield_pct")
        growth_val = stats.get("growth_12m_pct")
        demand = stats.get("rental_demand_score", 50)
        yield_pts = min(float(yield_val or 0) / 6.0 * 35, 35) if yield_val else 0
        growth_pts = min(max(float(growth_val or 0) + 5, 0) / 15 * 30, 30) if growth_val is not None else 0
        demand_pts = float(demand) / 100 * 35
        if yield_val is None and growth_val is None:
            # Census-only profile — weight population/demand proxy
            pop = int(stats.get("population") or 0)
            demand_pts = min(pop / 50000, 1.0) * 50 + 25
            return int(round(min(demand_pts, 100)))
        return int(round(yield_pts + growth_pts + demand_pts))

    def hotspot_label(self, score: int) -> str:
        if score >= 75:
            return "Strong investor interest (discussion metric)"
        if score >= 55:
            return "Moderate investor interest (discussion metric)"
        return "Lower yield/growth mix — research carefully (discussion metric)"


_store: SuburbStatsStore | None = None


def get_store(persist_path: Path | None = None) -> SuburbStatsStore:
    global _store
    if _store is None:
        _store = SuburbStatsStore(persist_path)
    return _store
