#!/usr/bin/env python3
"""
Download all AU suburbs/localities and build a searchable SQLite index on PERSIST_PATH.

Run manually, on Railway deploy, or via Railway cron:
  python scripts/sync_suburbs.py

Source: michalsn/australian-suburbs (ABS 2016 census localities, MIT licence).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import urllib.request
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger("sync_suburbs")

SOURCE_URL = (
    "https://raw.githubusercontent.com/michalsn/australian-suburbs/master/data/suburbs.json"
)
PERSIST = Path(os.getenv("PERSIST_PATH", "/data"))
DB_PATH = PERSIST / "suburbs.db"
LEGACY_JSON = PERSIST / "suburbs.json"
META_PATH = PERSIST / "suburbs_sync_meta.json"


def _download_rows() -> list[dict]:
    logger.info(f"Downloading suburb dataset from {SOURCE_URL}")
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "ShadowBot-SuburbSync/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    rows = payload.get("data", payload if isinstance(payload, list) else [])
    logger.info(f"Downloaded {len(rows)} locality records")
    return rows


def _build_db(rows: list[dict]) -> int:
    PERSIST.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".tmp")
    if tmp.exists():
        tmp.unlink()

    conn = sqlite3.connect(tmp)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(
        """
        CREATE TABLE suburbs (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            name_lower TEXT NOT NULL,
            state TEXT NOT NULL,
            postcode INTEGER,
            population INTEGER,
            median_income INTEGER,
            sqkm REAL,
            lat REAL,
            lng REAL,
            lga TEXT,
            urban_area TEXT
        );
        CREATE INDEX idx_suburbs_name_lower ON suburbs(name_lower);
        CREATE INDEX idx_suburbs_state ON suburbs(state);
        """
    )

    inserted = 0
    legacy: dict[str, list[str]] = {}
    batch = []

    for row in rows:
        name = (row.get("suburb") or "").strip()
        state = (row.get("state") or "").strip().upper()
        if not name or not state:
            continue
        name_lower = name.lower()
        batch.append(
            (
                name,
                name_lower,
                state,
                row.get("postcode"),
                row.get("population"),
                row.get("median_income"),
                row.get("sqkm"),
                row.get("lat"),
                row.get("lng"),
                row.get("local_goverment_area") or row.get("local_government_area"),
                row.get("urban_area"),
            )
        )
        legacy.setdefault(state.lower(), [])
        if name not in legacy[state.lower()]:
            legacy[state.lower()].append(name)
        inserted += 1

    conn.executemany(
        """
        INSERT INTO suburbs (
            name, name_lower, state, postcode, population, median_income,
            sqkm, lat, lng, lga, urban_area
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        batch,
    )
    conn.commit()
    conn.close()
    tmp.replace(DB_PATH)

    for subs in legacy.values():
        subs.sort()
    with open(LEGACY_JSON, "w", encoding="utf-8") as f:
        json.dump(legacy, f, indent=2)

    with open(META_PATH, "w", encoding="utf-8") as f:
        json.dump({"records": inserted, "source": SOURCE_URL}, f, indent=2)

    logger.info(f"Built {DB_PATH} with {inserted} suburbs")
    logger.info(f"Wrote legacy {LEGACY_JSON}")
    return inserted


def main() -> int:
    try:
        rows = _download_rows()
        count = _build_db(rows)
        logger.info(f"Suburb sync complete — {count} localities indexed")
        return 0
    except Exception as e:
        logger.exception(f"Suburb sync failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
