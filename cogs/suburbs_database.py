import os
import json
import logging
from pathlib import Path

# ==========================================
# TELEMETRY & LOGGING
# ==========================================
logger = logging.getLogger("ShadowSyn.SuburbsDB")

# ==========================================
# CONFIGURATION & CONSTANTS
# ==========================================
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
SUBURBS_DB_PATH = PERSIST_ROOT / "suburbs.json"

# Clean, verified seed data. Zero LLM hallucinations.
SEED_SUBURBS = {
    "Sydney": [
        "Abbotsford", "Alexandria", "Annandale", "Artarmon", "Ashfield", "Auburn", "Avalon Beach", 
        "Balmain", "Bankstown", "Baulkham Hills", "Blacktown", "Bondi", "Bondi Beach", "Burwood",
        "Cabramatta", "Camden", "Campbelltown", "Campsie", "Castle Hill", "Chatswood", "Cherrybrook",
        "Concord", "Coogee", "Cronulla", "Crows Nest", "Croydon", "Darlinghurst", "Dee Why",
        "Double Bay", "Drummoyne", "Dulwich Hill", "Eastwood", "Edgecliff", "Epping", "Fairfield",
        "Glebe", "Gordon", "Guildford", "Hornsby", "Hurstville", "Kellyville", "Kensington",
        "Kingsford", "Kogarah", "Lane Cove", "Leichhardt", "Lidcombe", "Liverpool", "Manly",
        "Maroubra", "Marrickville", "Mascot", "Merrylands", "Mosman", "Newtown", "North Sydney",
        "Paddington", "Parramatta", "Penrith", "Petersham", "Punchbowl", "Pymble", "Randwick",
        "Redfern", "Rockdale", "Rose Bay", "Ryde", "Seven Hills", "Stanmore", "Strathfield",
        "Surry Hills", "Sutherland", "Sydenham", "Vaucluse", "Waterloo", "Waverley", "Westmead"
    ],
    "Melbourne": [
        "Abbotsford", "Albert Park", "Alphington", "Armadale", "Ascot Vale", "Balaclava", "Balwyn",
        "Box Hill", "Brighton", "Brunswick", "Bundoora", "Burwood", "Camberwell", "Carlton",
        "Carnegie", "Caulfield", "Chadstone", "Cheltenham", "Clayton", "Coburg", "Collingwood",
        "Craigieburn", "Cranbourne", "Dandenong", "Doncaster", "Elsternwick", "Eltham", "Elwood",
        "Essendon", "Fitzroy", "Flemington", "Footscray", "Frankston", "Glen Iris", "Glen Waverley",
        "Hawthorn", "Ivanhoe", "Kew", "Malvern", "Melbourne", "Mentone", "Moonee Ponds", "Moorabbin",
        "Newport", "Northcote", "Oakleigh", "Ormond", "Pakenham", "Prahran", "Preston", "Reservoir",
        "Richmond", "Ringwood", "Rowville", "South Yarra", "St Kilda", "Sunshine", "Tarneit",
        "Thornbury", "Toorak", "Werribee", "Williamstown", "Yarraville"
    ],
    "Brisbane": [
        "Albion", "Alderley", "Annerley", "Ascot", "Ashgrove", "Auchenflower", "Balmoral",
        "Bardon", "Bowen Hills", "Bulimba", "Camp Hill", "Cannon Hill", "Carindale", "Chermside",
        "Clayfield", "Coorparoo", "Corinda", "Dutton Park", "East Brisbane", "Eight Mile Plains",
        "Enoggera", "Everton Park", "Fairfield", "Fortitude Valley", "Graceville", "Hamilton",
        "Hawthorne", "Highgate Hill", "Holland Park", "Indooroopilly", "Kangaroo Point", "Kedron",
        "Kelvin Grove", "Kenmore", "Lutwyche", "Macgregor", "Milton", "Mitchelton", "Moorooka",
        "Morningside", "Mount Gravatt", "New Farm", "Newmarket", "Newstead", "Norman Park",
        "Nundah", "Paddington", "Red Hill", "Sherwood", "South Brisbane", "Spring Hill",
        "St Lucia", "Stafford", "Sunnybank", "Taringa", "Tarragindi", "Tennyson", "Toowong",
        "Upper Mount Gravatt", "West End", "Windsor", "Woolloongabba", "Wooloowin", "Yeerongpilly"
    ],
    "Perth": [
        "Applecross", "Armadale", "Balcatta", "Baldivis", "Bayswater", "Belmont", "Cannington",
        "Claremont", "Cottesloe", "Dianella", "Doubleview", "Duncraig", "East Perth", "Fremantle",
        "Gosnells", "Innaloo", "Joondalup", "Karrinyup", "Leederville", "Maylands", "Midland",
        "Morley", "Mosman Park", "Mount Lawley", "Nedlands", "Northbridge", "Osborne Park",
        "Peppermint Grove", "Perth", "Rockingham", "Scarborough", "South Perth", "Subiaco",
        "Swanbourne", "Victoria Park", "Wembley"
    ],
    "Adelaide": [
        "Adelaide", "Aldinga Beach", "Burnside", "Campbelltown", "Elizabeth", "Enfield",
        "Glenelg", "Golden Grove", "Goodwood", "Hallett Cove", "Hindmarsh", "Marion",
        "Mawson Lakes", "Mitcham", "Modbury", "Morphett Vale", "Mount Barker", "North Adelaide",
        "Norwood", "Parafield Gardens", "Payneham", "Port Adelaide", "Prospect", "Salisbury",
        "Seaford", "Semaphore", "Stirling", "Tea Tree Gully", "Unley", "Walkerville", "West Lakes"
    ]
}

# ==========================================
# DATABASE MANAGER
# ==========================================
class SuburbDatabase:
    """Manages autonomous provisioning and loading of the JSON suburbs dataset."""
    
    def __init__(self):
        self.suburbs_by_city = {}
        self.all_suburbs = []
        self.suburb_to_state = {}
        
        # Core routing map for the Scraper API
        self.state_map = {
            "Sydney": "nsw", "Melbourne": "vic", "Brisbane": "qld",
            "Perth": "wa", "Adelaide": "sa", "Hobart": "tas",
            "Darwin": "nt", "Canberra": "act"
        }
        
        self._initialize_db()

    def _atomic_write(self, file_path: Path, data: dict):
        """Atomic write to prevent corruption during deployment cycling."""
        try:
            content = json.dumps(data, indent=4)
            temp_path = file_path.with_suffix(".tmp")
            temp_path.write_text(content, encoding='utf-8')
            temp_path.replace(file_path)
        except Exception as e:
            logger.error(f"SuburbDB Persistence Error: {e}")

    def _initialize_db(self):
        """Loads from JSON or provisions it via SEED_SUBURBS if missing/corrupted."""
        if not SUBURBS_DB_PATH.exists():
            logger.info("suburbs.json not found. Provisioning with clean seed data.")
            self._atomic_write(SUBURBS_DB_PATH, SEED_SUBURBS)
            data = SEED_SUBURBS
        else:
            try:
                data = json.loads(SUBURBS_DB_PATH.read_text(encoding='utf-8'))
            except json.JSONDecodeError:
                logger.error("suburbs.json is corrupted. Re-provisioning with seed data.")
                self._atomic_write(SUBURBS_DB_PATH, SEED_SUBURBS)
                data = SEED_SUBURBS

        self.suburbs_by_city = data
        
        # Flatten and map to state vectors
        for city, suburbs in self.suburbs_by_city.items():
            state = self.state_map.get(city, "nsw")
            for sub in suburbs:
                clean_sub = sub.strip()
                self.all_suburbs.append(clean_sub)
                self.suburb_to_state[clean_sub.lower()] = state

        # Deduplicate and sort alphabetically
        self.all_suburbs = sorted(list(set(self.all_suburbs)))
        logger.info(f"✅ Loaded {len(self.all_suburbs)} verified Australian suburbs into memory cache.")

# ==========================================
# EXPORTED MODULE VARIABLES
# ==========================================
# The InvestBot scraper will import these variables directly.
db = SuburbDatabase()
ALL_AUSTRALIAN_SUBURBS = db.all_suburbs
SUBURB_TO_STATE = db.suburb_to_state

def setup(bot):
    """Empty setup to satisfy Py-cord's load_extension if registered as a cog."""
    pass
