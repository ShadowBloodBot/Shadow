"""Searchable AU suburb index — SQLite on PERSIST_PATH, built by scripts/sync_suburbs.py."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from pathlib import Path

logger = logging.getLogger("ShadowSyn.SuburbsDB")

PERSIST = Path(os.getenv("PERSIST_PATH", "/data"))
DB_PATH = PERSIST / "suburbs.db"
_REPO_SEED = Path(__file__).resolve().parent.parent / "data" / "suburbs_seed.json"


class SuburbDatabase:
    def __init__(self):
        self.all_suburbs: list[str] = []
        self.suburb_to_state: dict[str, str] = {}
        self._conn: sqlite3.Connection | None = None
        self._load()

    def _connect(self) -> sqlite3.Connection | None:
        if not DB_PATH.exists():
            return None
        if self._conn is None:
            self._conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _load_legacy_json(self):
        paths = [PERSIST / "suburbs.json", _REPO_SEED]
        for path in paths:
            if not path.exists():
                continue
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
                for state, suburbs in data.items():
                    for sub in suburbs:
                        clean = sub.strip()
                        if clean and clean not in self.all_suburbs:
                            self.all_suburbs.append(clean)
                        self.suburb_to_state[clean.lower()] = state.lower()
                logger.info(f"Loaded suburbs from {path.name}")
                return
            except Exception as e:
                logger.error(f"Failed to parse {path}: {e}")

    def _load_from_sqlite(self):
        conn = self._connect()
        if not conn:
            return False
        cur = conn.execute("SELECT name, state FROM suburbs ORDER BY name")
        for row in cur.fetchall():
            name = row["name"]
            state = row["state"].lower()
            if name not in self.all_suburbs:
                self.all_suburbs.append(name)
            self.suburb_to_state[name.lower()] = state
        logger.info(f"Loaded {len(self.all_suburbs)} suburbs from SQLite index")
        return True

    def _load(self):
        if not self._load_from_sqlite():
            self._load_legacy_json()
        self.all_suburbs = sorted(set(self.all_suburbs))
        if DB_PATH.exists():
            logger.info(f"Suburb search DB ready: {DB_PATH}")
        elif not self.all_suburbs:
            logger.error("No suburb data — run scripts/sync_suburbs.py on Railway")

    def reload(self):
        if self._conn:
            self._conn.close()
            self._conn = None
        self.all_suburbs.clear()
        self.suburb_to_state.clear()
        self._load()

    def search(self, query: str, limit: int = 15) -> list[str]:
        q = (query or "").strip().lower()
        conn = self._connect()
        if conn and q:
            cur = conn.execute(
                """
                SELECT name FROM suburbs
                WHERE name_lower LIKE ? OR name_lower LIKE ?
                ORDER BY
                    CASE WHEN name_lower LIKE ? THEN 0 ELSE 1 END,
                    population DESC,
                    name
                LIMIT ?
                """,
                (f"{q}%", f"%{q}%", f"{q}%", limit),
            )
            hits = [r["name"] for r in cur.fetchall()]
            if hits:
                return hits
        if not q:
            return self.all_suburbs[:limit]
        hits = [s for s in self.all_suburbs if s.lower().startswith(q)]
        if len(hits) < limit:
            hits += [s for s in self.all_suburbs if q in s.lower() and s not in hits]
        return hits[:limit]

    def get_record(self, name: str) -> dict | None:
        conn = self._connect()
        if not conn:
            return None
        cur = conn.execute(
            "SELECT * FROM suburbs WHERE name_lower = ? LIMIT 1",
            (name.lower().strip(),),
        )
        row = cur.fetchone()
        return dict(row) if row else None


db = SuburbDatabase()
ALL_AUSTRALIAN_SUBURBS = db.all_suburbs
SUBURB_TO_STATE = db.suburb_to_state


def setup(bot):
    pass
