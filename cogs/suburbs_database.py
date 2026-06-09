import json
import logging
from pathlib import Path
import os

logger = logging.getLogger("ShadowSyn.SuburbsDB")

class SuburbDatabase:
    def __init__(self):
        self.all_suburbs = []
        self.suburb_to_state = {}
        self.db_path = Path(os.getenv("PERSIST_PATH", "/data")) / "suburbs.json"
        self._load()

    def _load(self):
        if not self.db_path.exists():
            logger.error(f"CRITICAL: {self.db_path} not found.")
            return

        try:
            with open(self.db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Flatten structure for O(1) lookups
                for state, suburbs in data.items():
                    for sub in suburbs:
                        clean_sub = sub.strip()
                        self.all_suburbs.append(clean_sub)
                        self.suburb_to_state[clean_sub.lower()] = state.lower()
                
                self.all_suburbs = sorted(list(set(self.all_suburbs)))
                logger.info(f"✅ Loaded {len(self.all_suburbs)} suburbs from {self.db_path.name}")
        except Exception as e:
            logger.error(f"Failed to parse suburbs JSON: {e}")

# Initialization
db = SuburbDatabase()
ALL_AUSTRALIAN_SUBURBS = db.all_suburbs
SUBURB_TO_STATE = db.suburb_to_state

def setup(bot):
    pass
