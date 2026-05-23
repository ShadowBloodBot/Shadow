# cogs/spire.py
import os
import json
import random
import traceback
from pathlib import Path
from typing import Dict, List, Any

import discord
from discord import Option, ButtonStyle, Interaction
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

# --- CARD & ENTITY MATRIX ---
CLASSES = {
    "Vanguard": {
        "desc": "Heavy armor and kinetic force.",
        "hp": 80,
        "deck": [
            "strike", "strike", "strike", "strike", 
            "defend", "defend", "defend", "defend", "breach"
        ]
    },
    "Phantom": {
        "desc": "Agile assassin. Relies on Poison and rapid strikes.",
        "hp": 70,
        "deck": [
            "strike", "strike", "strike", "strike", 
            "defend", "defend", "defend", "defend", "acid_flask"
        ]
    },
    "Netrunner": {
        "desc": "Tech specialist. Manipulates Energy.",
        "hp": 75,
        "deck": [
            "strike", "strike", "strike", "strike", 
            "defend", "defend", "defend", "defend", "overclock"
        ]
    }
}

CARDS = {
    "strike": {
        "name": "Strike", 
        "cost": 1, 
        "type": "Attack", 
        "dmg": 6, 
        "desc": "Deal 6 DMG.",
        "tags": ["Basic"]
    },
    "defend": {
        "name": "Defend", 
        "cost": 1, 
        "type": "Skill", 
        "blk": 5, 
        "desc": "Gain 5 Block.",
        "tags": ["Basic"]
    },
    "breach": {
        "name": "Breach", 
        "cost": 2, 
        "type": "Attack", 
        "dmg": 8, 
        "apply": {"vuln": 2}, 
        "desc": "Deal 8 DMG. Apply 2 Vulnerable.",
        "tags": ["Debuff"]
    },
    "iron_wave": {
        "name": "Iron Wave", 
        "cost": 1, 
        "type": "Attack", 
        "dmg": 5, 
        "blk": 5, 
        "desc": "Gain 5 Block. Deal 5 DMG.",
        "tags": ["Hybrid"]
    },
    "inflame": {
        "name": "Inflame", 
        "cost": 1, 
        "type": "Power", 
        "apply_self": {"str": 2}, 
        "desc": "Gain 2 Strength. (Exhausts)", 
        "exhaust": True,
        "tags": ["Scaling"]
    },
    "cleave": {
        "name": "Cleave", 
        "cost": 1, 
        "type": "Attack", 
        "dmg": 8, 
        "desc": "Deal 8 DMG.",
        "tags": ["Standard"]
    },
    "heavy_blade": {
        "name": "Heavy Blade", 
        "cost": 3, 
        "type": "Attack", 
        "dmg": 14, 
        "str_mult": 3, 
        "desc": "Deal 14 DMG. Str affects this 3x.",
        "tags": ["Finisher", "Scaling"]
    },
    "acid_flask": {
        "name": "Acid Flask", 
        "cost": 1, 
        "type": "Skill", 
        "apply": {"corrosion": 4}, 
        "desc": "Apply 4 Corrosion.",
        "tags": ["Corrosion Engine"]
    },
    "flurry": {
        "name": "Flurry", 
        "cost": 0, 
        "type": "Attack", 
        "dmg": 4, 
        "desc": "Deal 4 DMG.",
        "tags": ["Zero-Cost"]
    },
    "deadly_poison": {
        "name": "Deadly Poison", 
        "cost": 1, 
        "type": "Skill", 
        "apply": {"corrosion": 5}, 
        "desc": "Apply 5 Corrosion.",
        "tags": ["Corrosion Engine"]
    },
    "backflip": {
        "name": "Backflip", 
        "cost": 1, 
        "type": "Skill", 
        "blk": 5, 
        "draw": 2, 
        "desc": "Gain 5 Block. Draw 2 cards.",
        "tags": ["Engine"]
    },
    "bane": {
        "name": "Bane", 
        "cost": 1, 
        "type": "Attack", 
        "dmg": 7, 
        "bane": True, 
        "desc": "Deal 7 DMG. Deal again if Corroded.",
        "tags": ["Combo"]
    },
    "overclock": {
        "name": "Overclock", 
        "cost": 0, 
        "type": "Skill", 
        "energy": 1, 
        "draw": 1, 
        "desc": "Gain 1 NRG. Draw 1. (Exhausts)", 
        "exhaust": True,
        "tags": ["Engine"]
    },
    "glitch": {
        "name": "Glitch", 
        "cost": 1, 
        "type": "Attack", 
        "dmg": 7, 
        "apply": {"weak": 1}, 
        "desc": "Deal 7 DMG. Apply 1 Weak.",
        "tags": ["Debuff"]
    },
    "compile": {
        "name": "Compile", 
        "cost": 2, 
        "type": "Skill", 
        "blk": 10, 
        "draw": 2, 
        "desc": "Gain 10 Block. Draw 2 cards.",
        "tags": ["Engine"]
    },
    "laser": {
        "name": "Orbital Laser", 
        "cost": 2, 
        "type": "Attack", 
        "dmg": 15, 
        "desc": "Deal 15 DMG.",
        "tags": ["Heavy"]
    },
    "reboot": {
        "name": "Reboot", 
        "cost": 3, 
        "type": "Skill", 
        "desc": "Shuffle Discard to Draw. Draw 5.", 
        "special": "reboot", 
        "exhaust": True,
        "tags": ["Engine"]
    }
}

ENEMIES = {
    1: [{"name": "Scrap Drone", "hp": 20, "pattern": [{"dmg": 5}, {"blk": 5}, {"dmg": 6}]}],
    2: [{"name": "Corrupt Guard", "hp": 35, "pattern": [{"dmg": 8}, {"apply": {"weak": 1}}, {"dmg": 10}]}],
    3: [{"name": "Cyber-Hound", "hp": 55, "pattern": [{"dmg": 12}, {"blk": 10}, {"dmg": 15}]}],
    4: [{"name": "Black-ICE", "hp": 80, "pattern": [{"dmg": 10, "apply": {"vuln": 1}}, {"dmg": 18}, {"blk": 15}]}],
    5: [{"name": "CEO Boss", "hp": 150, "pattern": [{"dmg": 15}, {"blk": 20, "apply_self": {"str": 2}}, {"dmg": 25}]}],
    "elite_1": [{"name": "Hunter Killer", "hp": 65, "pattern": [{"dmg": 12, "apply": {"vuln": 1}}, {"dmg": 16}]}],
    "elite_2": [{"name": "SysAdmin", "hp": 110, "pattern": [{"blk": 20}, {"dmg": 20}, {"apply": {"weak": 2, "vuln": 1}}]}]
}

# --- STATE MANAGEMENT ---
def init_player(user_id: str) -> Dict:
    needs_save = False
    if user_id not in spire_db:
        spire_db[user_id] = {}
        needs_save = True

    d = spire_db[user_id]
    
    schema_matrix = {
        "runs": 0, 
        "victories": 0, 
        "active_run": None,
        "credits": 0, 
        "bounty": 0, 
        "kills": 0, 
        "deaths": 0, 
        "data_shards": 0, 
        "sector": 1,
        "defense_grid": [],
        "last_deck": []
    }

    for key, default_value in schema_matrix.items():
        if key not in d: 
            d[key] = default_value
            needs_save = True
            
    if needs_save:
        _save_db()
        
    return d

def generate_map_nodes(floor: int) -> List[str]:
    if floor == 5:
        return ["boss"]
    
    pool = ["combat", "combat", "elite", "safehouse"]
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
        "combat": None,
        "next_nodes": generate_map_nodes(1),
        "log": [f"{ANSI_YELLOW}System Initialized.{ANSI_RESET}"]
    }
    spire_db[user_id]["active_run"] = run
    _save_db()
    return run

def clear_run(user_id: str):
    spire_db[str(user_id)]["active_run"] = None
    _save_db()

# --- COMBAT ENGINE ---
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
        "energy": run["max_energy"]
    }
    random.shuffle(run["combat"]["draw_pile"])
    run["log"] = [f"{ANSI_RED}Engaged: {e_name}!{ANSI_RESET}"]
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
        if c["p_status"][stat] > 0: 
            c["p_status"][stat] -= 1
        if c["e_status"][stat] > 0: 
            c["e_status"][stat] -= 1

    c["turn"] += 1
    c["p_block"] = 0
    c["discard_pile"].extend(c["hand"])
    c["hand"] = []
    c["energy"] = run["max_energy"]
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
            out.append(f"⚔️ {dmg_val} ➡️ [🛡️ {c['p_block']}] ➡️ 🟢 Blocked")
        else:
            out.append(f"⚔️ {dmg_val} ➡️ [🛡️ {c['p_block']}] ➡️ 🩸 -{net_dmg} HP")
    if "blk" in intent:
        out.append(f"🛡️ {intent['blk']} BLK")
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
                
                creds = random.randint(15, 30)
                spire_db[uid_str]["credits"] += creds
                _save_db()
                
                vic_view = RewardView(view.user_id, view.run)
                vic_embed = view.build_victory_embed(creds, vic_view.choices)
                return await interaction.response.edit_message(embed=vic_embed, view=vic_view)
        
        _save_db()
        next_embed = view.build_embed()
        next_view = CombatView(view.user_id, view.run)
        await interaction.response.edit_message(embed=next_embed, view=next_view)

class CombatView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        self.render_hand()

    def render_hand(self):
        c = self.run["combat"]
        current_energy = c["energy"]
        
        type_order = {"Attack": 0, "Skill": 1, "Power": 2}
        c["hand"].sort(key=lambda card_id: type_order.get(CARDS[card_id]["type"], 3))

        for idx, card_id in enumerate(c["hand"][:5]):
            self.add_item(HandCardButton(idx, card_id, 0, current_energy))
        
        btn = Button(label="End Turn", style=ButtonStyle.success, row=1)
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
        
        e_hp = str(c["e_hp"])
        e_max = str(c["e_max_hp"])
        e_blk = str(c["e_block"])
        
        e_stat = f"**HP:** {e_hp}/{e_max} | **Block:** {e_blk}"
        if c["e_status"]["vuln"] > 0: 
            e_stat += f"\n> **Vuln: {c['e_status']['vuln']}** *(DMG Taken x1.5)*"
        if c["e_status"]["weak"] > 0: 
            e_stat += f"\n> **Weak: {c['e_status']['weak']}** *(ATK x0.75)*"
        if c["e_status"]["corrosion"] > 0: 
            e_stat += f"\n> **Corr: {c['e_status']['corrosion']}** *(Takes true DMG every turn)*"
            
        i_str = get_enemy_intent_string(self.run)
        embed.add_field(name="Target Entity", value=e_stat + f"\n\n**Intent:** {i_str}", inline=False)
        
        p_hp = str(self.run["hp"])
        p_max = str(self.run["max_hp"])
        p_blk = str(c["p_block"])
        
        nrg = c["energy"]
        max_nrg = self.run["max_energy"]
        energy_visual = ("⚡" * nrg) + ("🌑" * (max_nrg - nrg))
        
        p_stat = f"**HP:** {p_hp}/{p_max} | **Block:** {p_blk}\n**Energy:** {energy_visual}"
        
        if c["p_status"]["str"] > 0: 
            p_stat += f"\n> **Str: {c['p_status']['str']}** *(+DMG to attacks)*"
        if c["p_status"]["vuln"] > 0: 
            p_stat += f"\n> **Vuln: {c['p_status']['vuln']}** *(DMG Taken x1.5)*"
        if c["p_status"]["weak"] > 0: 
            p_stat += f"\n> **Weak: {c['p_status']['weak']}** *(ATK x0.75)*"
            
        embed.add_field(name=f"Operator ({self.run['char']})", value=p_stat, inline=False)
        
        log_lines = self.run["log"][-8:]
        log_text = "\n".join(log_lines)
        ansi_log = f"```ansi\n{log_text}\n```"
        embed.add_field(name="System Log", value=ansi_log, inline=False)
        
        draw_atk = sum(1 for cid in c["draw_pile"] if CARDS[cid]["type"] == "Attack")
        draw_skl = sum(1 for cid in c["draw_pile"] if CARDS[cid]["type"] == "Skill")
        draw_pwr = sum(1 for cid in c["draw_pile"] if CARDS[cid]["type"] == "Power")
        
        d_len = str(len(c["draw_pile"]))
        dis_len = str(len(c["discard_pile"]))
        ex_len = str(len(c["exhaust_pile"]))
        
        ftr = f"Draw: {d_len} [⚔️ {draw_atk} | 🛡️ {draw_skl} | ⚡ {draw_pwr}] | Disc: {dis_len} | Exh: {ex_len}"
        embed.set_footer(text=ftr)
        
        return embed

    def build_victory_embed(self, creds_won: int, choices: List[str] = None) -> discord.Embed:
        r_hp = str(self.run["hp"])
        r_max = str(self.run["max_hp"])
        
        embed = discord.Embed(
            title="Threat Neutralized", 
            description="Area clear. Accessing root nodes...", 
            color=THEME_HACK
        )
        embed.add_field(name="Integrity", value=f"HP: {r_hp}/{r_max}")
        embed.add_field(name="Loot", value=f"{creds_won} CR")
        
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
        pool = []
        for cid in CARDS.keys():
            if cid not in ["strike", "defend"]: 
                pool.append(cid)
        return random.sample(pool, min(3, len(pool)))

    def render_rewards(self):
        for idx, card_id in enumerate(self.choices):
            c_name = CARDS[card_id]["name"]
            c_cost = str(CARDS[card_id]["cost"])
            
            btn = Button(label=f"[{c_cost}] {c_name}", style=ButtonStyle.primary, row=0)
            btn.custom_id = "reward_" + str(idx)
            btn.callback = self.claim_reward
            self.add_item(btn)
            
        skip_btn = Button(label="Skip (+10 CR, +5 HP)", style=ButtonStyle.secondary, row=1)
        skip_btn.custom_id = "skip_reward"
        skip_btn.callback = self.claim_reward
        self.add_item(skip_btn)

    async def claim_reward(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("Unauthorized.", ephemeral=True)
        
        uid_str = str(self.user_id)
        cid = interaction.data.get("custom_id")
        
        if cid == "skip_reward":
            spire_db[uid_str]["credits"] += 10
            self.run["hp"] = min(self.run["max_hp"], self.run["hp"] + 5)
        else:
            idx = int(cid.split("_")[1])
            self.run["deck"].append(self.choices[idx])
            
        if self.run["floor"] > 5:
            spire_db[uid_str]["victories"] += 1
            spire_db[uid_str]["sector"] += 1
            spire_db[uid_str]["data_shards"] += 1
            
            # Defense Grid snapshot
            best_cards = [c for c in self.run["deck"] if c not in ["strike", "defend"]]
            spire_db[uid_str]["defense_grid"] = best_cards[:5] if best_cards else ["strike"] * 5
            spire_db[uid_str]["last_deck"] = self.run["deck"].copy()
            
            clear_run(self.user_id)
            _save_db()
            
            win_embed = discord.Embed(
                title="RUN COMPLETE", 
                description="Megacorp Spire conquered. Sector advanced. Defense Grid updated.", 
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

    @discord.slash_command(
        name="spire", 
        description="Infiltrate the Megacorp Spire."
    )
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
                else:
                    view = MapView(ctx.author.id, run)
                    map_embed = discord.Embed(
                        title="Navigation Matrix", 
                        description="Select your next infiltration vector.", 
                        color=THEME_DARK_PURPLE
                    )
                    await safe_reply(ctx, embed=map_embed, view=view)
            else:
                sel_embed = discord.Embed(title="Select Operator", color=THEME_CYAN)
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

    @discord.slash_command(
        name="spire_abandon", 
        description="Terminate your active run."
    )
    async def spire_abandon(self, ctx: discord.ApplicationContext):
        uid = str(ctx.author.id)
        if uid in spire_db and spire_db[uid].get("active_run"):
            clear_run(uid)
            await safe_reply(ctx, "Run terminated. Save cleared.")
        else:
            await safe_reply(ctx, "No active run found.", ephemeral=True)

    @discord.slash_command(
        name="spire_heist", 
        description="Invade a target network's Defense Grid."
    )
    async def spire_heist(
        self, 
        ctx: discord.ApplicationContext, 
        target: Option(discord.Member, description="Target to hack.")
    ):
        try:
            if ctx.author.id == target.id: 
                msg = "Cannot target own network."
                return await safe_reply(ctx, msg, ephemeral=True)
            
            uid_1 = str(ctx.author.id)
            uid_2 = str(target.id)
            
            u1 = init_player(uid_1)
            u2 = init_player(uid_2)
            
            if u2["runs"] == 0 and u2["sector"] == 1:
                return await safe_reply(ctx, "Target inactive.", ephemeral=True)
                
            if not u1.get("last_deck"):
                return await safe_reply(ctx, "You must complete a Spire run to establish a deck first.", ephemeral=True)
            
            # Defense Grid Auto-Battler Logic
            def calculate_power(deck: List[str]) -> int:
                power = 0
                for cid in deck:
                    if cid in CARDS:
                        card = CARDS[cid]
                        power += card.get("dmg", 0) * 2
                        power += card.get("blk", 0) * 1.5
                        power += card.get("cost", 1) * 3
                return int(power)

            atk_power = calculate_power(random.sample(u1["last_deck"], min(5, len(u1["last_deck"]))))
            atk_power += (u1.get("sector", 1) * 10) + random.randint(1, 20)
            
            def_grid = u2.get("defense_grid", ["strike", "defend"])
            def_power = calculate_power(def_grid)
            def_power += (u2.get("sector", 1) * 10) + random.randint(1, 20)

            embed = discord.Embed(title="Shadow-Net Breach", color=THEME_PINK)
            embed.add_field(name="Attacker Logic", value=f"Power Rating: {atk_power}")
            embed.add_field(name="Defender Grid", value=f"Power Rating: {def_power}")
            
            if atk_power > def_power:
                stolen = int(u2["credits"] * 0.15)
                u2["credits"] -= stolen
                u1["credits"] += stolen + u2["bounty"]
                u1["kills"] += 1
                u2["deaths"] += 1
                
                msg = f"{ctx.author.display_name} breached {target.display_name}'s grid.\n\nStolen: {stolen} CR"
                if u2["bounty"] > 0:
                    msg += f"\nBounty Claimed: {u2['bounty']} CR"
                u2["bounty"] = 0
                
                embed.description = msg
                embed.color = THEME_HACK
            else:
                stolen = int(u1["credits"] * 0.15)
                u1["credits"] -= stolen
                u2["credits"] += stolen
                u2["kills"] += 1
                u1["deaths"] += 1
                
                msg = f"{ctx.author.display_name} was isolated by {target.display_name}'s Defense Grid.\n\nLost: {stolen} CR\nConnection severed."
                
                embed.description = msg
                embed.color = THEME_PINK

            _save_db()
            await safe_reply(ctx, embed=embed)
        except Exception as e:
            await safe_reply(ctx, "Error: " + str(e), ephemeral=True)

    @discord.slash_command(
        name="spire_bounty", 
        description="Place a hit on a rival."
    )
    async def spire_bounty(
        self, 
        ctx: discord.ApplicationContext, 
        target: Option(discord.Member, description="Target player"), 
        amount: Option(int, description="Credits to place on bounty")
    ):
        if amount <= 0: 
            return await safe_reply(ctx, "Must be > 0.", ephemeral=True)
        
        u1 = init_player(str(ctx.author.id))
        if u1["credits"] < amount: 
            return await safe_reply(ctx, "Insufficient funds.", ephemeral=True)
            
        u2 = init_player(str(target.id))
        u1["credits"] -= amount
        u2["bounty"] += amount
        _save_db()
        
        b_embed = discord.Embed(
            title="Contract Issued", 
            description=f"Bounty of {amount} CR placed on {target.display_name}.", 
            color=THEME_CORP
        )
        await safe_reply(ctx, embed=b_embed)

    @discord.slash_command(
        name="spire_board", 
        description="View the Shadow-Net Leaderboard."
    )
    async def spire_board(self, ctx: discord.ApplicationContext):
        p_list = [(uid, data) for uid, data in spire_db.items() if isinstance(data, dict)]
                
        if not p_list: 
            return await safe_reply(ctx, "No data.", ephemeral=True)
        
        embed = discord.Embed(title="The Shadow-Net", color=THEME_CYAN)
        
        top_inf = sorted(p_list, key=lambda x: x[1].get("sector", 0), reverse=True)[:5]
        i_lines = [f"<@{u}>: Sector {d.get('sector', 0)}" for u, d in top_inf]
        inf_str = "\n".join(i_lines) if i_lines else "None"
        
        top_hack = sorted(p_list, key=lambda x: x[1].get("kills", 0), reverse=True)[:5]
        h_lines = [f"<@{u}>: {d.get('kills', 0)} Hacks" for u, d in top_hack if d.get("kills", 0) > 0]
        hack_str = "\n".join(h_lines) if h_lines else "None"
        
        embed.add_field(name="Top Infiltrators", value=inf_str, inline=False)
        embed.add_field(name="Apex Hackers", value=hack_str, inline=False)
        await safe_reply(ctx, embed=embed)

def setup(bot):
    bot.add_cog(SpireCog(bot))
