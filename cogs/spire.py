# cogs/spire.py
import os
import json
import random
import traceback
from pathlib import Path
from typing import Dict, List, Any

import discord
from discord import Option, ButtonStyle, Interaction, SelectOption
from discord.ui import View, Button, Select
from discord.ext import commands

# --- SYSTEM CONSTANTS ---
THEME_DARK_PURPLE = 0x2B0B35
THEME_CYAN = 0x00F0FF 
THEME_PINK = 0xFF003C 
THEME_HACK = 0x00FF00 
THEME_CORP = 0xFCEE0A

ANSI_CYAN = "\u001b[36m"
ANSI_RED = "\u001b[31m"
ANSI_GREEN = "\u001b[32m"
ANSI_YELLOW = "\u001b[33m"
ANSI_RESET = "\u001b[0m"

# Architectural Rule: Single server only. Bind commands directly to the guild cache.
# IMPORTANT: Replace this with your actual Quinfall server ID before deploying.
TARGET_GUILD_ID = 123456789012345678 
# Hybrid Security Architecture Role ID
SPIRE_ROLE_ID = 955600320287887400

# --- INFRASTRUCTURE & PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve() 
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print("[SYSTEM WARN] Using fallback local directory. Error: " + str(e))
    PERSIST_ROOT = Path(".").resolve()

SPIRE_STORE = (PERSIST_ROOT / "spire_db.json") 
spire_db: Dict[str, Any] = {}

def _atomic_write(file_path: Path, data: Any):
    try:
        content = json.dumps(data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding="utf-8")
        temp_path.replace(file_path)
    except Exception as e:
        msg = "[SYSTEM ERR] Persistence Failure: " + str(e)
        print(msg) 

def _save_db(): 
    _atomic_write(SPIRE_STORE, spire_db)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, "respond"):
            return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, "response"):
            if not ctx_or_inter.response.is_done():
                return await ctx_or_inter.response.send_message(*args, **kwargs)
            else:
                return await ctx_or_inter.followup.send(*args, **kwargs)
    except discord.NotFound:
        pass
    except Exception as e:
        print("[SYSTEM WARN] Reply Execution Failed: " + str(e))
    return None 

# --- UI UTILITIES ---
def _render_bar(val: int, max_val: int, length: int = 12) -> str:
    """Generates an ASCII progress bar for HP."""
    if max_val <= 0: return "░" * length
    filled = max(0, min(length, int((val / max_val) * length)))
    return "█" * filled + "░" * (length - filled)

# --- PROGRESSION & UNLOCK ENGINE ---
def get_player_level(user_id: str) -> int:
    d = spire_db.get(str(user_id), {})
    runs = d.get("runs", 0)
    victories = d.get("victories", 0)
    return (runs // 3) + (victories * 2) + 1

# --- GAME DATA MATRIX ---
CLASSES = {
    "Vanguard": {
        "desc": "Heavy armor and kinetic force.",
        "hp": 80,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "breach"]
    },
    "Phantom": {
        "desc": "Agile assassin. Relies on Poison and rapid strikes.",
        "hp": 70,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "acid_flask"]
    },
    "Netrunner": {
        "desc": "Tech specialist. Manipulates Energy.",
        "hp": 75,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "overclock"]
    }
}

CARDS = {
    "strike": {"name": "Strike", "cost": 1, "type": "Attack", "dmg": 6, "desc": "Deal 6 DMG.", "tags": ["Basic"], "req_lvl": 1},
    "defend": {"name": "Defend", "cost": 1, "type": "Skill", "blk": 5, "desc": "Gain 5 Block.", "tags": ["Basic"], "req_lvl": 1},
    "breach": {"name": "Breach", "cost": 2, "type": "Attack", "dmg": 8, "apply": {"vuln": 2}, "desc": "Deal 8 DMG. Apply 2 Vuln.", "tags": ["Debuff"], "req_lvl": 1},
    "iron_wave": {"name": "Iron Wave", "cost": 1, "type": "Attack", "dmg": 5, "blk": 5, "desc": "Gain 5 Blk. Deal 5 DMG.", "tags": ["Hybrid"], "req_lvl": 1},
    "inflame": {"name": "Inflame", "cost": 1, "type": "Power", "apply_self": {"str": 2}, "desc": "Gain 2 Str. (Exhausts)", "exhaust": True, "tags": ["Scaling"], "req_lvl": 1},
    "cleave": {"name": "Cleave", "cost": 1, "type": "Attack", "dmg": 8, "desc": "Deal 8 DMG.", "tags": ["Standard"], "req_lvl": 1},
    "acid_flask": {"name": "Acid Flask", "cost": 1, "type": "Skill", "apply": {"corrosion": 4}, "desc": "Apply 4 Corr.", "tags": ["Corrosion"], "req_lvl": 1},
    "overclock": {"name": "Overclock", "cost": 0, "type": "Skill", "energy": 1, "draw": 1, "desc": "Gain 1 NRG. Draw 1. (Exhausts)", "exhaust": True, "tags": ["Engine"], "req_lvl": 1},
    "heavy_blade": {"name": "Heavy Blade", "cost": 3, "type": "Attack", "dmg": 14, "str_mult": 3, "desc": "Deal 14 DMG. Str affects this 3x.", "tags": ["Finisher"], "req_lvl": 2},
    "reboot": {"name": "Reboot", "cost": 3, "type": "Skill", "desc": "Shuffle Discard to Draw. Draw 5.", "special": "reboot", "exhaust": True, "tags": ["Engine"], "req_lvl": 2},
    "laser": {"name": "Orbital Laser", "cost": 2, "type": "Attack", "dmg": 15, "desc": "Deal 15 DMG.", "tags": ["Heavy"], "req_lvl": 3},
    "bane": {"name": "Bane", "cost": 1, "type": "Attack", "dmg": 7, "bane": True, "desc": "Deal 7 DMG. Deal again if Corroded.", "tags": ["Combo"], "req_lvl": 3},
    "glitch": {"name": "Glitch", "cost": 1, "type": "Attack", "dmg": 7, "apply": {"weak": 1}, "desc": "Deal 7 DMG. Apply 1 Weak.", "tags": ["Debuff"], "req_lvl": 4},
    "compile": {"name": "Compile", "cost": 2, "type": "Skill", "blk": 10, "draw": 2, "desc": "Gain 10 Block. Draw 2 cards.", "tags": ["Engine"], "req_lvl": 4}
}

RELICS = {
    "blood_vial": {"name": "Blood Vial", "desc": "Heal 2 HP at the start of combat.", "tier": 1, "req_lvl": 1},
    "vajra": {"name": "Vajra Core", "desc": "Gain 1 Strength at the start of combat.", "tier": 2, "req_lvl": 1},
    "anchor": {"name": "Heavy Anchor", "desc": "Gain 10 Block on turn 1.", "tier": 1, "req_lvl": 2},
    "battery": {"name": "Fusion Battery", "desc": "Gain +1 Max Energy.", "tier": 3, "req_lvl": 3},
    "toxin_gland": {"name": "Toxin Gland", "desc": "Apply 1 Corrosion to all enemies turn 1.", "tier": 2, "req_lvl": 4}
}

POTIONS = {
    "block_pot": {"name": "Shield Stim", "desc": "Gain 12 Block.", "tier": 1, "req_lvl": 1},
    "str_pot": {"name": "Adrenaline Shot", "desc": "Gain 2 Strength.", "tier": 1, "req_lvl": 1},
    "energy_pot": {"name": "Plasma Cell", "desc": "Gain 2 Energy.", "tier": 2, "req_lvl": 2},
    "heal_pot": {"name": "Nano-Meds", "desc": "Heal 15 HP.", "tier": 2, "req_lvl": 3}
}

ENEMIES = {
    1: [{"name": "Scrap Drone", "hp": 25, "pattern": [{"blk": 5, "apply_self": {"str": 1}}, {"dmg": 6}, {"dmg": 8}]}],
    2: [{"name": "Corrupt Guard", "hp": 40, "pattern": [{"blk": 10}, {"apply": {"weak": 1, "vuln": 1}}, {"dmg": 12}]}],
    3: [{"name": "Cyber-Hound", "hp": 60, "pattern": [{"dmg": 6}, {"dmg": 6}, {"blk": 15, "apply_self": {"str": 2}}, {"dmg": 15}]}],
    4: [{"name": "Black-ICE", "hp": 85, "pattern": [{"apply": {"vuln": 2}}, {"dmg": 15}, {"blk": 20}, {"dmg": 20}]}],
    5: [{"name": "CEO Boss", "hp": 200, "pattern": [{"apply_self": {"str": 2}, "blk": 20}, {"dmg": 15}, {"apply": {"corrosion": 3, "weak": 2}}, {"dmg": 25}, {"blk": 30}]}],
    "elite_1": [{"name": "Hunter Killer", "hp": 75, "pattern": [{"apply_self": {"str": 2}, "blk": 10}, {"apply": {"vuln": 2}}, {"dmg": 18}]}],
    "elite_2": [{"name": "SysAdmin", "hp": 130, "pattern": [{"blk": 25, "apply": {"weak": 2}}, {"dmg": 15}, {"apply_self": {"str": 3}}, {"dmg": 25}]}]
}

# --- STATE MANAGEMENT ---
def init_player(user_id: str) -> Dict:
    needs_save = False
    if user_id not in spire_db:
        spire_db[user_id] = {}
        needs_save = True

    d = spire_db[user_id]
    
    schema_matrix = {
        "runs": 0, "victories": 0, "active_run": None,
        "credits": 0, "bounty": 0, "kills": 0, "deaths": 0, 
        "data_shards": 0, "sector": 1, "defense_grid": [], "last_deck": []
    }

    for key, default_value in schema_matrix.items():
        if key not in d: 
            d[key] = default_value
            needs_save = True
            
    if needs_save: _save_db()
    return d

def generate_map_nodes(floor: int) -> List[str]:
    if floor == 4:
        return ["safehouse"] 
    if floor == 5:
        return ["boss"]
    
    pool = ["combat", "merchant", "elite", "safehouse"]
    choices = random.sample(pool, 3)
    if "combat" not in choices and "elite" not in choices:
        choices[0] = "combat"
    return choices

def create_run(user_id: str, char_class: str):
    base_hp = CLASSES[char_class]["hp"]
    base_deck = CLASSES[char_class]["deck"].copy()
    
    run = {
        "char": char_class,
        "hp": base_hp,
        "max_hp": base_hp,
        "floor": 1,
        "max_energy": 3,
        "deck": base_deck,
        "relics": [],
        "potions": [],
        "gold": 99, 
        "combat": None,
        "shop": None,
        "next_nodes": generate_map_nodes(1),
        "log": [f"{ANSI_YELLOW}System Initialized.{ANSI_RESET}"]
    }
    spire_db[user_id]["active_run"] = run
    _save_db()
    return run

def clear_run(user_id: str):
    spire_db[str(user_id)]["active_run"] = None
    _save_db()

# --- ITEM & UNLOCK POOLS ---
def get_pool(item_type: str, player_lvl: int) -> List[str]:
    if item_type == "cards":
        return [k for k, v in CARDS.items() if v.get("req_lvl", 1) <= player_lvl and k not in ["strike", "defend"]]
    elif item_type == "relics":
        return [k for k, v in RELICS.items() if v.get("req_lvl", 1) <= player_lvl]
    elif item_type == "potions":
        return [k for k, v in POTIONS.items() if v.get("req_lvl", 1) <= player_lvl]
    return []

# --- COMBAT ENGINE ---
def trigger_relics(run: Dict, timing: str):
    c = run["combat"]
    for rel_id in run["relics"]:
        if timing == "combat_start":
            if rel_id == "blood_vial":
                run["hp"] = min(run["max_hp"], run["hp"] + 2)
                run["log"].append(f"{ANSI_GREEN}[Relic] Blood Vial healed 2 HP.{ANSI_RESET}")
            elif rel_id == "vajra":
                c["p_status"]["str"] = c["p_status"].get("str", 0) + 1
                run["log"].append(f"{ANSI_GREEN}[Relic] Vajra granted 1 Str.{ANSI_RESET}")
            elif rel_id == "toxin_gland":
                c["e_status"]["corrosion"] = c["e_status"].get("corrosion", 0) + 1
                run["log"].append(f"{ANSI_GREEN}[Relic] Toxin Gland applied 1 Corr.{ANSI_RESET}")
        elif timing == "turn_1":
            if rel_id == "anchor":
                c["p_block"] += 10
                run["log"].append(f"{ANSI_GREEN}[Relic] Anchor granted 10 Block.{ANSI_RESET}")

def init_combat(run: Dict, node_type: str = "combat"):
    floor = min(run["floor"], 5)
    
    if node_type == "boss":
        enemy_template = random.choice(ENEMIES[5])
    elif node_type == "elite":
        elite_tier = "elite_2" if floor >= 3 else "elite_1"
        enemy_template = random.choice(ENEMIES[elite_tier])
    else:
        enemy_template = random.choice(ENEMIES[floor])
        
    e_name = enemy_template["name"]
    e_hp = enemy_template["hp"]
    
    max_e = run["max_energy"]
    if "battery" in run["relics"]:
        max_e += 1

    run["combat"] = {
        "enemy": e_name,
        "e_hp": e_hp,
        "e_max_hp": e_hp,
        "pattern": enemy_template["pattern"],
        "turn": 0,
        "e_block": 0,
        "p_block": 0,
        "e_status": {"vuln": 0, "weak": 0, "corrosion": 0, "str": 0},
        "p_status": {"vuln": 0, "weak": 0, "str": 0},
        "draw_pile": run["deck"].copy(),
        "hand": [],
        "discard_pile": [],
        "exhaust_pile": [],
        "energy": max_e,
        "max_e": max_e
    }
    random.shuffle(run["combat"]["draw_pile"])
    run["log"] = [f"{ANSI_RED}Engaged: {e_name}!{ANSI_RESET}"]
    
    trigger_relics(run, "combat_start")
    trigger_relics(run, "turn_1")
    draw_cards(run, 5)

def draw_cards(run: Dict, count: int):
    c = run["combat"]
    for _ in range(count):
        if not c["draw_pile"]:
            if not c["discard_pile"]:
                break 
            c["draw_pile"] = c["discard_pile"].copy()
            c["discard_pile"] = []
            random.shuffle(c["draw_pile"])
        if len(c["hand"]) < 10:
            c["hand"].append(c["draw_pile"].pop())

def apply_damage(amount: int, is_player_source: bool, run: Dict) -> int:
    c = run["combat"]
    if is_player_source:
        a_stat = c["p_status"]
        d_stat = c["e_status"]
    else:
        a_stat = c["e_status"]
        d_stat = c["p_status"]
    
    amount += a_stat.get("str", 0)
    if a_stat.get("weak", 0) > 0:
        amount = int(amount * 0.75)
    if d_stat.get("vuln", 0) > 0:
        amount = int(amount * 1.5)
        
    return max(0, amount)

def deal_damage_to_enemy(run: Dict, dmg: int):
    c = run["combat"]
    if c["e_block"] > 0:
        blocked = min(c["e_block"], dmg)
        c["e_block"] -= blocked
        dmg -= blocked
    c["e_hp"] -= dmg

def deal_damage_to_player(run: Dict, dmg: int):
    c = run["combat"]
    if c["p_block"] > 0:
        blocked = min(c["p_block"], dmg)
        c["p_block"] -= blocked
        dmg -= blocked
    run["hp"] -= dmg

def use_potion(run: Dict, pot_idx: int) -> bool:
    if pot_idx >= len(run["potions"]): return False
    pot_id = run["potions"].pop(pot_idx)
    pot = POTIONS[pot_id]
    c = run["combat"]
    
    if pot_id == "block_pot":
        c["p_block"] += 12
    elif pot_id == "str_pot":
        c["p_status"]["str"] = c["p_status"].get("str", 0) + 2
    elif pot_id == "energy_pot":
        c["energy"] += 2
    elif pot_id == "heal_pot":
        run["hp"] = min(run["max_hp"], run["hp"] + 15)
        
    run["log"].append(f"{ANSI_CYAN}[Operator] Injected {pot['name']}{ANSI_RESET}")
    return True

def execute_card(run: Dict, card_idx: int) -> bool:
    c = run["combat"]
    if card_idx >= len(c["hand"]): 
        return False
    
    card_id = c["hand"][card_idx]
    card = CARDS[card_id]
    c_name = card["name"]
    c_cost = card["cost"]
    
    if c["energy"] < c_cost:
        run["log"].append(f"{ANSI_YELLOW}[!] Not enough energy for {c_name}{ANSI_RESET}")
        return False
        
    c["energy"] -= c_cost
    c["hand"].pop(card_idx)
    run["log"].append(f"{ANSI_CYAN}[Operator] Played {c_name}{ANSI_RESET}")
    
    if "blk" in card:
        c["p_block"] += card["blk"]
    
    if "dmg" in card:
        base_dmg = card["dmg"]
        if "str_mult" in card:
            p_str = c["p_status"].get("str", 0)
            base_dmg += (p_str * (card["str_mult"] - 1))
        dmg = apply_damage(base_dmg, True, run)
        deal_damage_to_enemy(run, dmg)
        
        has_corr = c["e_status"].get("corrosion", 0) > 0
        if card.get("bane", False) and has_corr:
            deal_damage_to_enemy(run, dmg)
            run["log"].append(f"{ANSI_CYAN}[Operator] Bane combo triggered!{ANSI_RESET}")

    if "apply" in card:
        for k, v in card["apply"].items():
            c["e_status"][k] = c["e_status"].get(k, 0) + v
            
    if "apply_self" in card:
        for k, v in card["apply_self"].items():
            c["p_status"][k] = c["p_status"].get(k, 0) + v
            
    if "energy" in card:
        c["energy"] += card["energy"]
        
    if "draw" in card:
        draw_cards(run, card["draw"])
        
    if card.get("special") == "reboot":
        c["draw_pile"].extend(c["discard_pile"])
        c["discard_pile"] = []
        random.shuffle(c["draw_pile"])
        draw_cards(run, 5)

    if card.get("exhaust", False):
        c["exhaust_pile"].append(card_id)
    else:
        c["discard_pile"].append(card_id)
        
    return True

def process_enemy_turn(run: Dict):
    c = run["combat"]
    
    if c["e_status"].get("corrosion", 0) > 0:
        corr_dmg = c["e_status"]["corrosion"]
        c["e_hp"] -= corr_dmg
        c["e_status"]["corrosion"] -= 1
        run["log"].append(f"{ANSI_GREEN}[Status] Target took {corr_dmg} Corr DMG{ANSI_RESET}")
        if c["e_hp"] <= 0: 
            return
        
    pattern_idx = c["turn"] % len(c["pattern"])
    intent = c["pattern"][pattern_idx]
    
    c["e_block"] = 0
    cur_turn = str(c["turn"] + 1)
    run["log"].append(f"{ANSI_RED}--- Target Turn {cur_turn} ---{ANSI_RESET}")
    
    if "blk" in intent:
        c["e_block"] += intent["blk"]
        run["log"].append(f"{ANSI_RED}[Target] Gained {intent['blk']} Blk{ANSI_RESET}")
        
    if "apply_self" in intent:
        for k, v in intent["apply_self"].items():
            c["e_status"][k] = c["e_status"].get(k, 0) + v
            
    if "apply" in intent:
        for k, v in intent["apply"].items():
            c["p_status"][k] = c["p_status"].get(k, 0) + v
            run["log"].append(f"{ANSI_RED}[Target] Applied {v} {k.capitalize()}{ANSI_RESET}")
            
    if "dmg" in intent:
        dmg = apply_damage(intent["dmg"], False, run)
        deal_damage_to_player(run, dmg)
        run["log"].append(f"{ANSI_RED}[Target] Dealt {dmg} DMG{ANSI_RESET}")

    for stat in ["vuln", "weak"]:
        if c["p_status"][stat] > 0: c["p_status"][stat] -= 1
        if c["e_status"][stat] > 0: c["e_status"][stat] -= 1

    c["turn"] += 1
    c["p_block"] = 0
    c["discard_pile"].extend(c["hand"])
    c["hand"] = []
    c["energy"] = c["max_e"]
    draw_cards(run, 5)

def get_enemy_intent_string(run: Dict) -> str:
    c = run["combat"]
    pattern_idx = c["turn"] % len(c["pattern"])
    intent = c["pattern"][pattern_idx]
    
    out = []
    if "dmg" in intent:
        dmg_val = apply_damage(intent["dmg"], False, run)
        net_dmg = max(0, dmg_val - c["p_block"])
        if net_dmg == 0:
            out.append(f"⚔️ `{dmg_val}` ➡️ [🛡️ `{c['p_block']}`] ➡️ 🟢 Blocked")
        else:
            out.append(f"⚔️ `{dmg_val}` ➡️ [🛡️ `{c['p_block']}`] ➡️ 🩸 -{net_dmg} HP")
    if "blk" in intent:
        out.append(f"🛡️ `{intent['blk']}` Defend")
    if "apply" in intent:
        out.append("⚠️ Debuff")
    if "apply_self" in intent:
        out.append("📈 Buff")
    
    if len(out) > 0:
        return " | ".join(out)
    return "Idle"

# --- UI COMPONENTS ---
class HandCardButton(Button):
    def __init__(self, card_idx: int, card_id: str, row: int, current_energy: int):
        card = CARDS[card_id]
        c_name = card["name"]
        c_cost = card["cost"]
        c_desc = card.get("desc", "")
        
        if card["type"] == "Attack":
            btn_style = ButtonStyle.danger 
        elif card["type"] == "Skill" and "blk" in card:
            btn_style = ButtonStyle.primary 
        else:
            btn_style = ButtonStyle.secondary 
            
        label_text = f"[{c_cost}] {c_name} | {c_desc}"
        if len(label_text) > 80:
            label_text = label_text[:77] + "..."
            
        is_disabled = current_energy < c_cost
            
        super().__init__(
            label=label_text,
            style=btn_style,
            row=row,
            disabled=is_disabled
        )
        self.card_idx = card_idx

    async def callback(self, interaction: Interaction):
        view: CombatView = self.view
        uid_str = str(view.user_id)
        
        if interaction.user.id != view.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
        
        success = execute_card(view.run, self.card_idx)
        if success:
            if view.run["combat"]["e_hp"] <= 0:
                view.run["combat"] = None
                view.run["floor"] += 1
                view.run["next_nodes"] = generate_map_nodes(view.run["floor"])
                
                gold_won = random.randint(15, 30)
                if view.run["floor"] > 5: gold_won += 50
                view.run["gold"] += gold_won
                
                _save_db()
                
                vic_view = RewardView(view.user_id, view.run)
                vic_embed = view.build_victory_embed(gold_won, vic_view.choices)
                return await interaction.response.edit_message(embed=vic_embed, view=vic_view)
        
        _save_db()
        next_embed = view.build_embed()
        next_view = CombatView(view.user_id, view.run)
        await interaction.response.edit_message(embed=next_embed, view=next_view)

class PotionSelect(Select):
    def __init__(self, run: Dict, row: int):
        options = []
        for idx, pot_id in enumerate(run["potions"]):
            pot = POTIONS[pot_id]
            options.append(SelectOption(label=f"Use {pot['name']}", value=str(idx), description=pot["desc"]))
        super().__init__(placeholder="Inject Potion...", min_values=1, max_values=1, options=options, row=row)

    async def callback(self, interaction: Interaction):
        view: CombatView = self.view
        if interaction.user.id != view.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
            
        pot_idx = int(self.values[0])
        use_potion(view.run, pot_idx)
        _save_db()
        
        next_embed = view.build_embed()
        next_view = CombatView(view.user_id, view.run)
        await interaction.response.edit_message(embed=next_embed, view=next_view)

class CombatView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        self.render_ui()

    def render_ui(self):
        c = self.run["combat"]
        current_energy = c["energy"]
        
        type_order = {"Attack": 0, "Skill": 1, "Power": 2}
        c["hand"].sort(key=lambda card_id: type_order.get(CARDS[card_id]["type"], 3))

        for idx, card_id in enumerate(c["hand"][:5]):
            self.add_item(HandCardButton(idx, card_id, 0, current_energy))
            
        if self.run["potions"]:
            self.add_item(PotionSelect(self.run, 1))
        
        btn = Button(label="End Turn", style=ButtonStyle.success, row=2)
        btn.callback = self.end_turn
        self.add_item(btn)

    async def end_turn(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
        
        process_enemy_turn(self.run)
        
        if self.run["hp"] <= 0:
            uid_str = str(self.user_id)
            spire_db[uid_str]["deaths"] += 1
            clear_run(self.user_id)
            
            dead_embed = discord.Embed(
                title="FLATLINED", 
                description="Your system has been purged.", 
                color=THEME_PINK
            )
            return await interaction.response.edit_message(embed=dead_embed, view=None)
            
        _save_db()
        next_embed = self.build_embed()
        next_view = CombatView(self.user_id, self.run)
        await interaction.response.edit_message(embed=next_embed, view=next_view)

    def build_embed(self) -> discord.Embed:
        c = self.run["combat"]
        f_num = str(self.run["floor"])
        
        embed = discord.Embed(
            title=f"Floor {f_num} | vs {c['enemy']}", 
            color=THEME_DARK_PURPLE
        )
        
        # UI Formatting Engine - Target
        e_hp_bar = _render_bar(c["e_hp"], c["e_max_hp"])
        e_stat = f"❤️ **HP:** `{c['e_hp']:02d} / {c['e_max_hp']:02d}`  `[{e_hp_bar}]`\n🛡️ **Block:** `{c['e_block']:02d}`"
        
        if c["e_status"]["vuln"] > 0: e_stat += f"\n> 📉 **Vuln: {c['e_status']['vuln']}** *(Takes 1.5x DMG)*"
        if c["e_status"]["weak"] > 0: e_stat += f"\n> ⚠️ **Weak: {c['e_status']['weak']}** *(Deals 0.75x DMG)*"
        if c["e_status"]["corrosion"] > 0: e_stat += f"\n> 🧪 **Corr: {c['e_status']['corrosion']}** *(Takes True DMG)*"
        if c["e_status"]["str"] > 0: e_stat += f"\n> 💪 **Str: {c['e_status']['str']}** *(+DMG Output)*"
            
        i_str = get_enemy_intent_string(self.run)
        embed.add_field(name=f"🤖 Target Entity: {c['enemy']}", value=e_stat + f"\n\n🔮 **Intent:** {i_str}", inline=False)
        
        # UI Formatting Engine - Operator
        p_hp_bar = _render_bar(self.run["hp"], self.run["max_hp"])
        p_stat = f"❤️ **HP:** `{self.run['hp']:02d} / {self.run['max_hp']:02d}`  `[{p_hp_bar}]`\n🛡️ **Block:** `{c['p_block']:02d}`"
        
        nrg = c["energy"]
        max_nrg = c["max_e"]
        energy_visual = ("⚡" * nrg) + ("🌑" * (max_nrg - nrg))
        p_stat += f"\n🔋 **Energy:** {energy_visual}"
        
        if c["p_status"]["str"] > 0: p_stat += f"\n> 💪 **Str: {c['p_status']['str']}** *(+DMG Output)*"
        if c["p_status"]["vuln"] > 0: p_stat += f"\n> 📉 **Vuln: {c['p_status']['vuln']}** *(Takes 1.5x DMG)*"
        if c["p_status"]["weak"] > 0: p_stat += f"\n> ⚠️ **Weak: {c['p_status']['weak']}** *(Deals 0.75x DMG)*"
            
        embed.add_field(name=f"👤 Operator ({self.run['char']})", value=p_stat, inline=False)
        
        # UI Formatting Engine - Logs & Meta
        log_lines = self.run["log"][-8:]
        log_text = "\n".join(log_lines)
        ansi_log = f"```ansi\n{log_text}\n
```"
        embed.add_field(name="🖥️ System Log", value=ansi_log, inline=False)
        
        d_len = str(len(c["draw_pile"]))
        dis_len = str(len(c["discard_pile"]))
        ex_len = str(len(c["exhaust_pile"]))
        
        relics_str = ", ".join([RELICS[r]["name"] for r in self.run["relics"]]) if self.run["relics"] else "None"
        embed.add_field(name="⚙️ Hardware Relics", value=relics_str, inline=False)
        
        ftr = f"Draw: {d_len} | Disc: {dis_len} | Exh: {ex_len} | Gold: {self.run['gold']} CR"
        embed.set_footer(text=ftr)
        
        return embed

    def build_victory_embed(self, gold_won: int, choices: List[str] = None) -> discord.Embed:
        r_hp = str(self.run["hp"])
        r_max = str(self.run["max_hp"])
        
        embed = discord.Embed(
            title="Threat Neutralized", 
            description="Area clear. Accessing root nodes...", 
            color=THEME_HACK
        )
        embed.add_field(name="Integrity", value=f"HP: {r_hp}/{r_max}")
        embed.add_field(name="Loot", value=f"{gold_won} Gold")
        
        if choices:
            r_text = ""
            for cid in choices:
                c = CARDS[cid]
                tags = ", ".join(c.get("tags", []))
                r_text += f"**{c['name']}** ({c['cost']} NRG) - *{c['desc']}* `[{tags}]`\n"
            embed.add_field(name="Available Upgrades", value=r_text, inline=False)
            
        return embed

class RewardView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        self.choices = self._generate_rewards()
        self.render_rewards()

    def _generate_rewards(self) -> List[str]:
        lvl = get_player_level(str(self.user_id))
        pool = get_pool("cards", lvl)
        return random.sample(pool, min(3, len(pool)))

    def render_rewards(self):
        for idx, card_id in enumerate(self.choices):
            c_name = CARDS[card_id]["name"]
            c_cost = str(CARDS[card_id]["cost"])
            
            btn = Button(label=f"[{c_cost}] {c_name}", style=ButtonStyle.primary, row=0)
            btn.custom_id = "reward_" + str(idx)
            btn.callback = self.claim_reward
            self.add_item(btn)
            
        skip_btn = Button(label="Skip (+10 Gold, +5 HP)", style=ButtonStyle.secondary, row=1)
        skip_btn.custom_id = "skip_reward"
        skip_btn.callback = self.claim_reward
        self.add_item(skip_btn)

    async def claim_reward(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
        
        uid_str = str(self.user_id)
        cid = interaction.data.get("custom_id")
        
        if cid == "skip_reward":
            self.run["gold"] += 10
            self.run["hp"] = min(self.run["max_hp"], self.run["hp"] + 5)
        else:
            idx = int(cid.split("_")[1])
            self.run["deck"].append(self.choices[idx])
            
        if self.run["floor"] > 5:
            spire_db[uid_str]["victories"] += 1
            spire_db[uid_str]["sector"] += 1
            spire_db[uid_str]["data_shards"] += 1
            spire_db[uid_str]["credits"] += self.run["gold"] 
            
            best_cards = [c for c in self.run["deck"] if c not in ["strike", "defend"]]
            spire_db[uid_str]["defense_grid"] = best_cards[:5] if best_cards else ["strike"] * 5
            spire_db[uid_str]["last_deck"] = self.run["deck"].copy()
            
            clear_run(self.user_id)
            _save_db()
            
            win_embed = discord.Embed(
                title="RUN COMPLETE", 
                description=f"Megacorp Spire conquered. Sector advanced. Extracted {self.run['gold']} CR to persistent balance.", 
                color=THEME_CYAN
            )
            return await interaction.response.edit_message(embed=win_embed, view=None)

        _save_db()
        map_embed = discord.Embed(
            title="Navigation Matrix", 
            description="Select your next infiltration vector.", 
            color=THEME_DARK_PURPLE
        )
        view = MapView(self.user_id, self.run)
        await interaction.response.edit_message(embed=map_embed, view=view)

class SafehouseView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        
        btn_heal = Button(label="Rest (Heal 30%)", style=ButtonStyle.success, emoji="🏕️")
        btn_heal.custom_id = "sh_heal"
        btn_heal.callback = self.process_choice
        self.add_item(btn_heal)
        
        btn_purge = Button(label="Purge Data (Remove 1 Card)", style=ButtonStyle.danger, emoji="🗑️")
        btn_purge.custom_id = "sh_purge"
        btn_purge.callback = self.process_choice
        self.add_item(btn_purge)

    async def process_choice(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
            
        cid = interaction.data.get("custom_id")
        msg = ""
        if cid == "sh_heal":
            heal_amt = int(self.run["max_hp"] * 0.3)
            self.run["hp"] = min(self.run["max_hp"], self.run["hp"] + heal_amt)
            msg = f"Rested. Recovered {heal_amt} HP."
        else:
            if "strike" in self.run["deck"]:
                self.run["deck"].remove("strike")
                msg = "Purged [Strike] from deck."
            elif "defend" in self.run["deck"]:
                self.run["deck"].remove("defend")
                msg = "Purged [Defend] from deck."
            else:
                self.run["deck"].pop(0)
                msg = "Purged a card from deck."
                
        self.run["floor"] += 1
        self.run["next_nodes"] = generate_map_nodes(self.run["floor"])
        _save_db()
        
        map_embed = discord.Embed(
            title="Safehouse Exited", 
            description=msg + "\nSelect your next infiltration vector.", 
            color=THEME_DARK_PURPLE
        )
        view = MapView(self.user_id, self.run)
        await interaction.response.edit_message(embed=map_embed, view=view)

class MerchantView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        self._init_shop_data()
        self.render_shop()

    def _init_shop_data(self):
        if not self.run.get("shop"):
            lvl = get_player_level(str(self.user_id))
            
            c_pool = get_pool("cards", lvl)
            r_pool = [r for r in get_pool("relics", lvl) if r not in self.run["relics"]]
            p_pool = get_pool("potions", lvl)
            
            cards = random.sample(c_pool, min(5, len(c_pool)))
            relics = random.sample(r_pool, min(3, len(r_pool)))
            potions = random.sample(p_pool, min(3, len(p_pool)))
            
            self.run["shop"] = {
                "cards": [{"id": c, "price": CARDS[c]["cost"] * 20 + 30} for c in cards],
                "relics": [{"id": r, "price": RELICS[r]["tier"] * 60 + 40} for r in relics],
                "potions": [{"id": p, "price": POTIONS[p]["tier"] * 25 + 20} for p in potions]
            }

    def render_shop(self):
        s = self.run["shop"]
        
        if s["cards"]:
            card_ops = [SelectOption(label=CARDS[x["id"]]["name"], value=f"c_{i}", description=f"{x['price']} Gold | {CARDS[x['id']]['desc']}") for i, x in enumerate(s["cards"])]
            card_sel = Select(placeholder="Purchase Cards...", options=card_ops, row=0)
            card_sel.callback = self.buy_item
            self.add_item(card_sel)
            
        if s["relics"]:
            rel_ops = [SelectOption(label=RELICS[x["id"]]["name"], value=f"r_{i}", description=f"{x['price']} Gold | {RELICS[x['id']]['desc']}") for i, x in enumerate(s["relics"])]
            rel_sel = Select(placeholder="Purchase Relics...", options=rel_ops, row=1)
            rel_sel.callback = self.buy_item
            self.add_item(rel_sel)
            
        if s["potions"]:
            pot_ops = [SelectOption(label=POTIONS[x["id"]]["name"], value=f"p_{i}", description=f"{x['price']} Gold | {POTIONS[x['id']]['desc']}") for i, x in enumerate(s["potions"])]
            pot_sel = Select(placeholder="Purchase Potions...", options=pot_ops, row=2)
            pot_sel.callback = self.buy_item
            self.add_item(pot_sel)
            
        leave_btn = Button(label="Leave Shop", style=ButtonStyle.danger, row=3)
        leave_btn.callback = self.leave_shop
        self.add_item(leave_btn)

    async def buy_item(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
            
        val = interaction.data["values"][0]
        i_type, idx = val.split("_")[0], int(val.split("_")[1])
        cat = "cards" if i_type == "c" else "relics" if i_type == "r" else "potions"
        
        item_data = self.run["shop"][cat][idx]
        price = item_data["price"]
        item_id = item_data["id"]
        
        if self.run["gold"] < price:
            return await interaction.response.send_message("Insufficient Gold.", ephemeral=True)
            
        if cat == "potions" and len(self.run["potions"]) >= 3:
            return await interaction.response.send_message("Potion slots full (Max 3).", ephemeral=True)
            
        self.run["gold"] -= price
        self.run["shop"][cat].pop(idx)
        
        if cat == "cards":
            self.run["deck"].append(item_id)
        elif cat == "relics":
            self.run["relics"].append(item_id)
        elif cat == "potions":
            self.run["potions"].append(item_id)
            
        _save_db()
        embed = build_shop_embed(self.run)
        new_view = MerchantView(self.user_id, self.run)
        await interaction.response.edit_message(embed=embed, view=new_view)

    async def leave_shop(self, interaction: Interaction):
        if interaction.user.id != self.user_id: return
        self.run["shop"] = None
        self.run["floor"] += 1
        self.run["next_nodes"] = generate_map_nodes(self.run["floor"])
        _save_db()
        
        map_embed = discord.Embed(
            title="Navigation Matrix", 
            description="Select your next infiltration vector.", 
            color=THEME_DARK_PURPLE
        )
        view = MapView(self.user_id, self.run)
        await interaction.response.edit_message(embed=map_embed, view=view)

def build_shop_embed(run: Dict) -> discord.Embed:
    embed = discord.Embed(
        title="Black Market Merchant",
        description=f"**Current Gold:** {run['gold']} CR\n\nTrade your credits for hardware upgrades.",
        color=THEME_CORP
    )
    return embed

class MapView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        
        nodes = run.get("next_nodes", generate_map_nodes(run["floor"]))
        
        for idx, n_type in enumerate(nodes):
            if n_type == "combat":
                btn = Button(label="Scraper Node", style=ButtonStyle.secondary, emoji="👾")
            elif n_type == "elite":
                btn = Button(label="Black-ICE Node", style=ButtonStyle.danger, emoji="☠️")
            elif n_type == "safehouse":
                btn = Button(label="Safehouse", style=ButtonStyle.success, emoji="🏕️")
            elif n_type == "merchant":
                btn = Button(label="Black Market", style=ButtonStyle.primary, emoji="🛒")
            elif n_type == "boss":
                btn = Button(label="CEO Executive Suite", style=ButtonStyle.danger, emoji="🏢")
                
            btn.custom_id = f"node_{n_type}_{idx}"
            btn.callback = self.select_node
            self.add_item(btn)

    async def select_node(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
            
        custom_id = interaction.data.get("custom_id", "")
        n_type = custom_id.split("_")[1]
        
        if n_type == "safehouse":
            embed = discord.Embed(
                title="Safehouse", 
                description="You found a secure terminal. What will you do?", 
                color=THEME_CYAN
            )
            view = SafehouseView(self.user_id, self.run)
            await interaction.response.edit_message(embed=embed, view=view)
        elif n_type == "merchant":
            view = MerchantView(self.user_id, self.run)
            embed = build_shop_embed(self.run)
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            init_combat(self.run, n_type)
            _save_db()
            view = CombatView(self.user_id, self.run)
            next_embed = view.build_embed()
            await interaction.response.edit_message(embed=next_embed, view=view)

class CharSelectView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        for c_name in CLASSES.keys():
            btn = Button(label=c_name, style=ButtonStyle.primary)
            btn.custom_id = "char_" + c_name
            btn.callback = self.select_char
            self.add_item(btn)

    async def select_char(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
            
        custom_id = interaction.data.get("custom_id", "")
        char_name = custom_id.split("_")[1]
        
        uid_str = str(self.user_id)
        init_player(uid_str)
        spire_db[uid_str]["runs"] += 1
        
        run = create_run(uid_str, char_name)
        
        map_embed = discord.Embed(
            title="Spire Infiltration", 
            description="Select your first insertion point.", 
            color=THEME_DARK_PURPLE
        )
        view = MapView(self.user_id, run)
        await interaction.response.edit_message(embed=map_embed, view=view)

# --- COG SETUP ---
class SpireCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        global spire_db
        if SPIRE_STORE.exists():
            try:
                raw_txt = SPIRE_STORE.read_text()
                spire_db = json.loads(raw_txt)
            except Exception as e:
                print("DB Load Failure: " + str(e))
                spire_db = {}
        else:
            spire_db = {}

    # =========================================================================
    # SECURE COMMAND DEPLOYMENT
    # =========================================================================

    @discord.slash_command(
        name="spire", 
        description="Infiltrate the Megacorp Spire.",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none()
    )
    @commands.has_role(SPIRE_ROLE_ID)
    async def spire(self, ctx: discord.ApplicationContext):
        try:
            uid = str(ctx.author.id)
            player = init_player(uid)
            
            if player.get("active_run"):
                run = player["active_run"]
                if run.get("combat"):
                    view = CombatView(ctx.author.id, run)
                    active_embed = view.build_embed()
                    await safe_reply(ctx, embed=active_embed, view=view)
                elif run.get("shop"):
                    view = MerchantView(ctx.author.id, run)
                    await safe_reply(ctx, embed=build_shop_embed(run), view=view)
                else:
                    view = MapView(ctx.author.id, run)
                    map_embed = discord.Embed(
                        title="Navigation Matrix", 
                        description="Select your next infiltration vector.", 
                        color=THEME_DARK_PURPLE
                    )
                    await safe_reply(ctx, embed=map_embed, view=view)
            else:
                lvl = get_player_level(uid)
                sel_embed = discord.Embed(title="Select Operator", description=f"**Current Sync Level:** {lvl}", color=THEME_CYAN)
                for name, data in CLASSES.items():
                    c_hp = str(data["hp"])
                    c_desc = str(data["desc"])
                    val_str = f"HP: {c_hp}\n{c_desc}"
                    sel_embed.add_field(name=name, value=val_str, inline=False)
                view = CharSelectView(ctx.author.id)
                await safe_reply(ctx, embed=sel_embed, view=view)
                
        except Exception as e:
            traceback.print_exc()
            await safe_reply(ctx, "Error: " + str(e), ephemeral=True)

    @spire.error
    async def spire_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(ctx, "🚫 System override denied: Missing Spire clearance role.", ephemeral=True)
        else:
            traceback.print_exception(type(error), error, error.__traceback__)

    @discord.slash_command(
        name="spire_abandon", 
        description="Terminate your active run.",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none()
    )
    @commands.has_role(SPIRE_ROLE_ID)
    async def spire_abandon(self, ctx: discord.ApplicationContext):
        uid = str(ctx.author.id)
        if uid in spire_db and spire_db[uid].get("active_run"):
            clear_run(uid)
            await safe_reply(ctx, "Run terminated. Save cleared.")
        else:
            await safe_reply(ctx, "No active run found.", ephemeral=True)

    @spire_abandon.error
    async def spire_abandon_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(ctx, "🚫 System override denied: Missing Spire clearance role.", ephemeral=True)
        else:
            traceback.print_exception(type(error), error, error.__traceback__)

def setup(bot):
    bot.add_cog(SpireCog(bot))
