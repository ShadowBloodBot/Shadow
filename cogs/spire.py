# cogs/spire.py
import os
import json
import random
import traceback
from pathlib import Path
from typing import Dict, List, Any

import discord
from discord import Option, ButtonStyle, Interaction
from discord.ui import View, Button
from discord.ext import commands

# --- SYSTEM CONSTANTS ---
THEME_DARK_PURPLE = 0x2B0B35
THEME_CYAN = 0x00F0FF 
THEME_PINK = 0xFF003C 
THEME_HACK = 0x00FF00 

# --- INFRASTRUCTURE & PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve() 
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except Exception as e:
    print(f"[SYSTEM WARN] Using fallback local directory. Error: {e}")
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
        print(f"[SYSTEM ERR] Persistence Failure during atomic write: {e}") 

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
        print(f"[SYSTEM WARN] Reply Execution Failed: {e}")
    return None 

# --- CARD & ENTITY MATRIX ---
CLASSES = {
    "Vanguard": {
        "desc": "Heavy armor and kinetic force. Relies on Strength and Block.",
        "emoji": "🛡️",
        "hp": 80,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "breach"]
    },
    "Phantom": {
        "desc": "Agile assassin. Relies on Corrosion (Poison) and rapid strikes.",
        "emoji": "🥷",
        "hp": 70,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "acid_flask"]
    },
    "Netrunner": {
        "desc": "Tech specialist. Manipulates Energy and rapid card cycling.",
        "emoji": "🔌",
        "hp": 75,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "overclock"]
    }
}

CARDS = {
    "strike": {"name": "Strike", "cost": 1, "type": "Attack", "dmg": 6, "desc": "Deal 6 DMG."},
    "defend": {"name": "Defend", "cost": 1, "type": "Skill", "blk": 5, "desc": "Gain 5 Block."},
    
    # Vanguard Pool
    "breach": {"name": "Breach", "cost": 2, "type": "Attack", "dmg": 8, "apply": {"vuln": 2}, "desc": "Deal 8 DMG. Apply 2 Vulnerable."},
    "iron_wave": {"name": "Iron Wave", "cost": 1, "type": "Attack", "dmg": 5, "blk": 5, "desc": "Gain 5 Block. Deal 5 DMG."},
    "inflame": {"name": "Inflame", "cost": 1, "type": "Power", "apply_self": {"str": 2}, "desc": "Gain 2 Strength. (Exhausts)", "exhaust": True},
    "cleave": {"name": "Cleave", "cost": 1, "type": "Attack", "dmg": 8, "desc": "Deal 8 DMG."},
    "heavy_blade": {"name": "Heavy Blade", "cost": 3, "type": "Attack", "dmg": 14, "str_mult": 3, "desc": "Deal 14 DMG. Strength affects this 3x."},
    
    # Phantom Pool
    "acid_flask": {"name": "Acid Flask", "cost": 1, "type": "Skill", "apply": {"corrosion": 4}, "desc": "Apply 4 Corrosion."},
    "flurry": {"name": "Flurry", "cost": 0, "type": "Attack", "dmg": 4, "desc": "Deal 4 DMG."},
    "deadly_poison": {"name": "Deadly Poison", "cost": 1, "type": "Skill", "apply": {"corrosion": 5}, "desc": "Apply 5 Corrosion."},
    "backflip": {"name": "Backflip", "cost": 1, "type": "Skill", "blk": 5, "draw": 2, "desc": "Gain 5 Block. Draw 2 cards."},
    "bane": {"name": "Bane", "cost": 1, "type": "Attack", "dmg": 7, "bane": True, "desc": "Deal 7 DMG. Deal it again if enemy has Corrosion."},

    # Netrunner Pool
    "overclock": {"name": "Overclock", "cost": 0, "type": "Skill", "energy": 1, "draw": 1, "desc": "Gain 1 Energy. Draw 1 card. (Exhausts)", "exhaust": True},
    "glitch": {"name": "Glitch", "cost": 1, "type": "Attack", "dmg": 7, "apply": {"weak": 1}, "desc": "Deal 7 DMG. Apply 1 Weak."},
    "compile": {"name": "Compile", "cost": 2, "type": "Skill", "blk": 10, "draw": 2, "desc": "Gain 10 Block. Draw 2 cards."},
    "laser": {"name": "Orbital Laser", "cost": 2, "type": "Attack", "dmg": 15, "desc": "Deal 15 DMG."},
    "reboot": {"name": "Reboot", "cost": 3, "type": "Skill", "desc": "Shuffle Discard into Draw. Draw 5.", "special": "reboot", "exhaust": True}
}

ENEMIES = {
    1: [{"name": "Scrap Drone", "hp": 20, "pattern": [{"dmg": 5}, {"blk": 5}, {"dmg": 6}]}],
    2: [{"name": "Corrupt Guard", "hp": 35, "pattern": [{"dmg": 8}, {"apply": {"weak": 1}}, {"dmg": 10}]}],
    3: [{"name": "Elite Cyber-Hound", "hp": 55, "pattern": [{"dmg": 12}, {"blk": 10}, {"dmg": 15}]}],
    4: [{"name": "Black-ICE Avatar", "hp": 80, "pattern": [{"dmg": 10, "apply": {"vuln": 1}}, {"dmg": 18}, {"blk": 15}]}],
    5: [{"name": "Megacorp CEO (Boss)", "hp": 150, "pattern": [{"dmg": 15}, {"blk": 20, "apply_self": {"str": 2}}, {"dmg": 25}]}]
}

# --- STATE MANAGEMENT ---
def init_player(user_id: str):
    if user_id not in spire_db:
        spire_db[user_id] = {"runs": 0, "victories": 0, "active_run": None}
    return spire_db[user_id]

def create_run(user_id: str, char_class: str):
    base_hp = CLASSES[char_class]["hp"]
    base_deck = CLASSES[char_class]["deck"].copy()
    
    run = {
        "char": char_class,
        "hp": base_hp,
        "max_hp": base_hp,
        "credits": 99,
        "floor": 1,
        "max_energy": 3,
        "deck": base_deck,
        "combat": None,
        "log": ["Run initialized."]
    }
    spire_db[user_id]["active_run"] = run
    _save_db()
    return run

def clear_run(user_id: str):
    spire_db[str(user_id)]["active_run"] = None
    _save_db()

# --- COMBAT ENGINE ---
def init_combat(run: Dict):
    floor = min(run["floor"], 5)
    enemy_template = random.choice(ENEMIES[floor])
    enemy_name = enemy_template["name"]
    enemy_hp = enemy_template["hp"]
    
    run["combat"] = {
        "enemy": enemy_name,
        "e_hp": enemy_hp,
        "e_max_hp": enemy_hp,
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
    run["log"] = [f"Engaged: {enemy_name}!"]
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
    attacker_status = c["p_status"] if is_player_source else c["e_status"]
    defender_status = c["e_status"] if is_player_source else c["p_status"]
    
    amount += attacker_status.get("str", 0)
    if attacker_status.get("weak", 0) > 0:
        amount = int(amount * 0.75)
    if defender_status.get("vuln", 0) > 0:
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
    card_name = card["name"]
    card_cost = card["cost"]
    
    if c["energy"] < card_cost:
        run["log"].append(f"❌ Not enough energy for {card_name}.")
        return False
        
    c["energy"] -= card_cost
    c["hand"].pop(card_idx)
    run["log"].append(f"> Played **{card_name}**.")
    
    # Process Effects
    if "blk" in card:
        c["p_block"] += card["blk"]
    
    if "dmg" in card:
        base_dmg = card["dmg"]
        if "str_mult" in card:
            base_dmg += (c["p_status"].get("str", 0) * (card["str_mult"] - 1))
        dmg = apply_damage(base_dmg, True, run)
        deal_damage_to_enemy(run, dmg)
        
        if card.get("bane", False) and c["e_status"].get("corrosion", 0) > 0:
            deal_damage_to_enemy(run, dmg)
            run["log"].append("Bane triggered twice!")

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
    
    # Apply Corrosion before turn execution
    if c["e_status"].get("corrosion", 0) > 0:
        corr_dmg = c["e_status"]["corrosion"]
        c["e_hp"] -= corr_dmg
        c["e_status"]["corrosion"] -= 1
        run["log"].append(f"Enemy takes {corr_dmg} Corrosion DMG.")
        if c["e_hp"] <= 0: 
            return
        
    pattern_idx = c["turn"] % len(c["pattern"])
    intent = c["pattern"][pattern_idx]
    
    c["e_block"] = 0
    current_turn = c["turn"]
    run["log"].append(f"Enemy turn [{current_turn}]:")
    
    if "blk" in intent:
        c["e_block"] += intent["blk"]
        blk_amt = intent["blk"]
        run["log"].append(f"Enemy gained {blk_amt} Block.")
    if "apply_self" in intent:
        for k, v in intent["apply_self"].items():
            c["e_status"][k] = c["e_status"].get(k, 0) + v
    if "apply" in intent:
        for k, v in intent["apply"].items():
            c["p_status"][k] = c["p_status"].get(k, 0) + v
            stat_name = str(k).capitalize()
            run["log"].append(f"Enemy applied {v} {stat_name}.")
    if "dmg" in intent:
        dmg = apply_damage(intent["dmg"], False, run)
        deal_damage_to_player(run, dmg)
        run["log"].append(f"Enemy dealt {dmg} DMG.")

    # Status Decay Phase
    for stat in ["vuln", "weak"]:
        if c["p_status"][stat] > 0: 
            c["p_status"][stat] -= 1
        if c["e_status"][stat] > 0: 
            c["e_status"][stat] -= 1

    # End Turn State Reset Phase
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
        dmg = apply_damage(intent["dmg"], False, run)
        out.append(f"⚔️ {dmg}")
    if "blk" in intent:
        blk_val = intent["blk"]
        out.append(f"🛡️ {blk_val}")
    if "apply" in intent:
        out.append("⚠️ Debuff")
    if "apply_self" in intent:
        out.append("📈 Buff")
    return " | ".join(out) if out else "💤 Idle"

# --- UI COMPONENTS ---
class HandCardButton(Button):
    def __init__(self, card_idx: int, card_id: str, row: int):
        card = CARDS[card_id]
        card_name = card["name"]
        card_cost = card["cost"]
        card_type = card["type"]
        
        btn_style = ButtonStyle.primary if card_type == "Attack" else ButtonStyle.secondary
        super().__init__(
            label=f"{card_name} ({card_cost})",
            style=btn_style,
            row=row
        )
        self.card_idx = card_idx

    async def callback(self, interaction: Interaction):
        view: CombatView = self.view
        if interaction.user.id != view.user_id: 
            return await interaction.response.send_message("🚫 Unauthorized.", ephemeral=True)
        
        success = execute_card(view.run, self.card_idx)
        if success:
            if view.run["combat"]["e_hp"] <= 0:
                view.run["combat"] = None
                view.run["floor"] += 1
                view.run["credits"] += random.randint(15, 30)
                _save_db()
                vic_embed = view.build_victory_embed()
                vic_view = RewardView(view.user_id, view.run)
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
        for idx, card_id in enumerate(c["hand"][:5]):
            self.add_item(HandCardButton(idx, card_id, 0))
        
        end_turn_btn = Button(label="End Turn", style=ButtonStyle.danger, row=1)
        end_turn_btn.callback = self.end_turn
        self.add_item(end_turn_btn)

    async def end_turn(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("🚫 Unauthorized.", ephemeral=True)
        
        process_enemy_turn(self.run)
        
        if self.run["hp"] <= 0:
            clear_run(self.user_id)
            dead_embed = discord.Embed(title="💀 FLATLINED", description="Your system has been purged.", color=THEME_PINK)
            return await interaction.response.edit_message(embed=dead_embed, view=None)
            
        _save_db()
        next_embed = self.build_embed()
        next_view = CombatView(self.user_id, self.run)
        await interaction.response.edit_message(embed=next_embed, view=next_view)

    def build_embed(self) -> discord.Embed:
        c = self.run["combat"]
        char_name = self.run["char"]
        char_emoji = CLASSES[char_name]["emoji"]
        floor_num = self.run["floor"]
        enemy_name = c["enemy"]
        
        embed = discord.Embed(title=f"Floor {floor_num} | 🆚 {enemy_name}", color=THEME_DARK_PURPLE)
        
        # Enemy Status Extraction
        e_hp = c["e_hp"]
        e_max = c["e_max_hp"]
        e_blk = c["e_block"]
        e_vuln = c["e_status"]["vuln"]
        e_weak = c["e_status"]["weak"]
        e_corr = c["e_status"]["corrosion"]
        
        e_stat = f"❤️ HP: {e_hp}/{e_max} | 🛡️ Blk: {e_blk}"
        if e_vuln > 0: e_stat += f"\n⚠️ Vuln: {e_vuln}"
        if e_weak > 0: e_stat += f"\n📉 Weak: {e_weak}"
        if e_corr > 0: e_stat += f"\n🧪 Corrosion: {e_corr}"
            
        intent_str = get_enemy_intent_string(self.run)
        embed.add_field(name="Target Entity", value=f"{e_stat}\n**Intent:** {intent_str}", inline=False)
        
        # Player Status Extraction
        p_hp = self.run["hp"]
        p_max = self.run["max_hp"]
        p_blk = c["p_block"]
        p_nrg = c["energy"]
        p_max_nrg = self.run["max_energy"]
        
        p_str = c["p_status"]["str"]
        p_vuln = c["p_status"]["vuln"]
        p_weak = c["p_status"]["weak"]
        
        p_stat = f"❤️ HP: {p_hp}/{p_max} | 🛡️ Blk: {p_blk}\n⚡ Energy: {p_nrg}/{p_max_nrg}"
        if p_str > 0: p_stat += f"\n💪 Str: {p_str}"
        if p_vuln > 0: p_stat += f"\n⚠️ Vuln: {p_vuln}"
        if p_weak > 0: p_stat += f"\n📉 Weak: {p_weak}"
            
        embed.add_field(name=f"{char_emoji} Operator ({char_name})", value=p_stat, inline=False)
        
        # Logs & Deck Info Block
        log_lines = self.run["log"][-5:]
        log_text = "\n".join(log_lines)
        embed.add_field(name="System Log", value=f"```ansi\n{log_text}\n
```", inline=False)
        
        draw_len = len(c["draw_pile"])
        disc_len = len(c["discard_pile"])
        exh_len = len(c["exhaust_pile"])
        embed.set_footer(text=f"Draw: {draw_len} | Discard: {disc_len} | Exhaust: {exh_len}")
        
        return embed

    def build_victory_embed(self) -> discord.Embed:
        run_hp = self.run["hp"]
        run_max = self.run["max_hp"]
        run_cred = self.run["credits"]
        
        embed = discord.Embed(title="✅ Threat Neutralized", description="Area clear. Accessing root nodes...", color=THEME_HACK)
        embed.add_field(name="Integrity", value=f"❤️ {run_hp}/{run_max}")
        embed.add_field(name="Credits", value=f"💳 {run_cred}")
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
        for cid, cdata in CARDS.items():
            if cid in ["strike", "defend"]: 
                continue
            pool.append(cid)
        return random.sample(pool, min(3, len(pool)))

    def render_rewards(self):
        for idx, card_id in enumerate(self.choices):
            card_name = CARDS[card_id]["name"]
            btn = Button(label=card_name, style=ButtonStyle.primary, row=0)
            btn.custom_id = f"reward_{idx}"
            btn.callback = self.claim_reward
            self.add_item(btn)
            
        skip_btn = Button(label="Skip", style=ButtonStyle.secondary, row=1)
        skip_btn.custom_id = "skip_reward"
        skip_btn.callback = self.claim_reward
        self.add_item(skip_btn)

    async def claim_reward(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("🚫 Unauthorized.", ephemeral=True)
        
        cid = interaction.data.get("custom_id")
        if cid != "skip_reward":
            idx = int(cid.split("_")[1])
            card = self.choices[idx]
            self.run["deck"].append(card)
            
        if self.run["floor"] > 5:
            clear_run(self.user_id)
            spire_db[str(self.user_id)]["victories"] += 1
            _save_db()
            win_embed = discord.Embed(title="🏆 RUN COMPLETE", description="You conquered the Megacorp Spire.", color=THEME_CYAN)
            return await interaction.response.edit_message(embed=win_embed, view=None)

        _save_db()
        map_embed = discord.Embed(title="Navigation", description="Move to the next sector?", color=THEME_DARK_PURPLE)
        await interaction.response.edit_message(embed=map_embed, view=MapView(self.user_id, self.run))

class MapView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        
        floor_num = run["floor"]
        btn = Button(label=f"Enter Floor {floor_num}", style=ButtonStyle.danger, emoji="⚔️")
        btn.callback = self.start_combat
        self.add_item(btn)

    async def start_combat(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("🚫 Unauthorized.", ephemeral=True)
            
        init_combat(self.run)
        _save_db()
        view = CombatView(self.user_id, self.run)
        next_embed = view.build_embed()
        await interaction.response.edit_message(embed=next_embed, view=view)

class CharSelectView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        for c_name, c_data in CLASSES.items():
            c_emoji = c_data["emoji"]
            btn = Button(label=c_name, style=ButtonStyle.primary, emoji=c_emoji)
            btn.custom_id = f"char_{c_name}"
            btn.callback = self.select_char
            self.add_item(btn)

    async def select_char(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("🚫 Unauthorized.", ephemeral=True)
            
        custom_id = interaction.data.get("custom_id", "")
        char_name = custom_id.split("_")[1]
        run = create_run(str(self.user_id), char_name)
        
        init_combat(run)
        _save_db()
        view = CombatView(self.user_id, run)
        next_embed = view.build_embed()
        await interaction.response.edit_message(embed=next_embed, view=view)

# --- COG SETUP ---
class SpireCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        global spire_db
        if SPIRE_STORE.exists():
            try:
                spire_db = json.loads(SPIRE_STORE.read_text())
            except Exception as e:
                print(f"[SYSTEM ERR] DB Load Failure: {e}")
                spire_db = {}
        else:
            spire_db = {}

    @discord.slash_command(name="spire", description="Infiltrate the Megacorp Spire (Slay the Spire 2 Style).")
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
                    map_embed = discord.Embed(title="Navigation", description="Resume infiltration.", color=THEME_DARK_PURPLE)
                    await safe_reply(ctx, embed=map_embed, view=view)
            else:
                sel_embed = discord.Embed(title="Select Your Operator", color=THEME_CYAN)
                for name, data in CLASSES.items():
                    c_emoji = data["emoji"]
                    c_hp = data["hp"]
                    c_desc = data["desc"]
                    sel_embed.add_field(name=f"{c_emoji} {name}", value=f"HP: {c_hp}\n{c_desc}", inline=False)
                view = CharSelectView(ctx.author.id)
                await safe_reply(ctx, embed=sel_embed, view=view)
                
        except Exception as e:
            traceback.print_exc()
            await safe_reply(ctx, f"⚠️ Core Exception: {e}", ephemeral=True)

    @discord.slash_command(name="spire_abandon", description="Terminate your active run.")
    async def spire_abandon(self, ctx: discord.ApplicationContext):
        uid = str(ctx.author.id)
        if uid in spire_db and spire_db[uid].get("active_run"):
            clear_run(uid)
            await safe_reply(ctx, "🛑 Run terminated. Save cleared.")
        else:
            await safe_reply(ctx, "❌ No active run found.", ephemeral=True)

def setup(bot):
    bot.add_cog(SpireCog(bot))
