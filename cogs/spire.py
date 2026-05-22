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
THEME_CORP = 0xFCEE0A

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
        "hp": 80,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "breach"]
    },
    "Phantom": {
        "desc": "Agile assassin. Relies on Corrosion (Poison) and rapid strikes.",
        "hp": 70,
        "deck": ["strike", "strike", "strike", "strike", "defend", "defend", "defend", "defend", "acid_flask"]
    },
    "Netrunner": {
        "desc": "Tech specialist. Manipulates Energy and rapid card cycling.",
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

# --- STATE MANAGEMENT & REGRESSION PROTECTION ---
def init_player(user_id: str):
    if user_id not in spire_db:
        spire_db[user_id] = {
            "runs": 0, "victories": 0, "active_run": None,
            "credits": 0, "bounty": 0, "kills": 0, "deaths": 0, "data_shards": 0, "sector": 1
        }
    d = spire_db[user_id]
    for key in ["credits", "bounty", "kills", "deaths", "data_shards", "sector"]:
        if key not in d: 
            d[key] = 0
    return d

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
    
    run["combat"] = {
        "enemy": enemy_template["name"],
        "e_hp": enemy_template["hp"],
        "e_max_hp": enemy_template["hp"],
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
    run["log"] = [f"Engaged: {enemy_template['name']}!"]
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
    
    if c["energy"] < card["cost"]:
        run["log"].append(f"[FAIL] Not enough energy for {card['name']}.")
        return False
        
    c["energy"] -= card["cost"]
    c["hand"].pop(card_idx)
    run["log"].append(f"> Played {card['name']}.")
    
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
    run["log"].append(f"Enemy turn [{c['turn']}]:")
    
    if "blk" in intent:
        c["e_block"] += intent["blk"]
        run["log"].append(f"Enemy gained {intent['blk']} Block.")
    if "apply_self" in intent:
        for k, v in intent["apply_self"].items():
            c["e_status"][k] = c["e_status"].get(k, 0) + v
    if "apply" in intent:
        for k, v in intent["apply"].items():
            c["p_status"][k] = c["p_status"].get(k, 0) + v
            run["log"].append(f"Enemy applied {v} {str(k).capitalize()}.")
    if "dmg" in intent:
        dmg = apply_damage(intent["dmg"], False, run)
        deal_damage_to_player(run, dmg)
        run["log"].append(f"Enemy dealt {dmg} DMG.")

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
        out.append(f"ATK: {apply_damage(intent['dmg'], False, run)}")
    if "blk" in intent:
        out.append(f"DEF: {intent['blk']}")
    if "apply" in intent:
        out.append("Debuff")
    if "apply_self" in intent:
        out.append("Buff")
    
    return " | ".join(out) if out else "Idle"

# --- UI COMPONENTS ---
class HandCardButton(Button):
    def __init__(self, card_idx: int, card_id: str, row: int):
        card = CARDS[card_id]
        btn_style = ButtonStyle.primary if card["type"] == "Attack" else ButtonStyle.secondary
        super().__init__(
            label=f"{card['name']} ({card['cost']})",
            style=btn_style,
            row=row
        )
        self.card_idx = card_idx

    async def callback(self, interaction: Interaction):
        view: CombatView = self.view
        
        if interaction.user.id != view.user_id: 
            return await interaction.response.send_message("[DENIED] Unauthorized.", ephemeral=True)
        
        success = execute_card(view.run, self.card_idx)
        if success:
            if view.run["combat"]["e_hp"] <= 0:
                view.run["combat"] = None
                view.run["floor"] += 1
                
                creds_won = random.randint(15, 30)
                spire_db[str(view.user_id)]["credits"] += creds_won
                _save_db()
                
                return await interaction.response.edit_message(
                    embed=view.build_victory_embed(creds_won), 
                    view=RewardView(view.user_id, view.run)
                )
        
        _save_db()
        await interaction.response.edit_message(
            embed=view.build_embed(), 
            view=CombatView(view.user_id, view.run)
        )

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
            return await interaction.response.send_message("[DENIED] Unauthorized.", ephemeral=True)
        
        process_enemy_turn(self.run)
        
        if self.run["hp"] <= 0:
            spire_db[str(self.user_id)]["deaths"] += 1
            clear_run(self.user_id)
            dead_embed = discord.Embed(title="FLATLINED", description="Your system has been purged.", color=THEME_PINK)
            return await interaction.response.edit_message(embed=dead_embed, view=None)
            
        _save_db()
        await interaction.response.edit_message(
            embed=self.build_embed(), 
            view=CombatView(self.user_id, self.run)
        )

    def build_embed(self) -> discord.Embed:
        c = self.run["combat"]
        
        embed = discord.Embed(
            title=f"Floor {self.run['floor']} | vs {c['enemy']}", 
            color=THEME_DARK_PURPLE
        )
        
        e_stat = f"HP: {c['e_hp']}/{c['e_max_hp']} | Blk: {c['e_block']}"
        if c["e_status"]["vuln"] > 0: e_stat += f"\nVuln: {c['e_status']['vuln']}"
        if c["e_status"]["weak"] > 0: e_stat += f"\nWeak: {c['e_status']['weak']}"
        if c["e_status"]["corrosion"] > 0: e_stat += f"\nCorrosion: {c['e_status']['corrosion']}"
            
        embed.add_field(
            name="Target Entity", 
            value=f"{e_stat}\n**Intent:** {get_enemy_intent_string(self.run)}", 
            inline=False
        )
        
        p_stat = f"HP: {self.run['hp']}/{self.run['max_hp']} | Blk: {c['p_block']}\nEnergy: {c['energy']}/{self.run['max_energy']}"
        if c["p_status"]["str"] > 0: p_stat += f"\nStr: {c['p_status']['str']}"
        if c["p_status"]["vuln"] > 0: p_stat += f"\nVuln: {c['p_status']['vuln']}"
        if c["p_status"]["weak"] > 0: p_stat += f"\nWeak: {c['p_status']['weak']}"
            
        embed.add_field(
            name=f"Operator ({self.run['char']})", 
            value=p_stat, 
            inline=False
        )
        
        log_text = "\n".join(self.run["log"][-5:])
        embed.add_field(
            name="System Log", 
            value=f"```ansi\n{log_text}\n
```", 
            inline=False
        )
        
        embed.set_footer(text=f"Draw: {len(c['draw_pile'])} | Discard: {len(c['discard_pile'])} | Exhaust: {len(c['exhaust_pile'])}")
        return embed

    def build_victory_embed(self, creds_won: int) -> discord.Embed:
        embed = discord.Embed(title="Threat Neutralized", description="Area clear. Accessing root nodes...", color=THEME_HACK)
        embed.add_field(name="Integrity", value=f"HP: {self.run['hp']}/{self.run['max_hp']}")
        embed.add_field(name="Loot Extracted", value=f"{creds_won} CR")
        return embed

class RewardView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        self.choices = self._generate_rewards()
        self.render_rewards()

    def _generate_rewards(self) -> List[str]:
        pool = [cid for cid in CARDS.keys() if cid not in ["strike", "defend"]]
        return random.sample(pool, min(3, len(pool)))

    def render_rewards(self):
        for idx, card_id in enumerate(self.choices):
            btn = Button(label=CARDS[card_id]["name"], style=ButtonStyle.primary, row=0)
            btn.custom_id = f"reward_{idx}"
            btn.callback = self.claim_reward
            self.add_item(btn)
            
        skip_btn = Button(label="Skip", style=ButtonStyle.secondary, row=1)
        skip_btn.custom_id = "skip_reward"
        skip_btn.callback = self.claim_reward
        self.add_item(skip_btn)

    async def claim_reward(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("[DENIED] Unauthorized.", ephemeral=True)
        
        cid = interaction.data.get("custom_id")
        if cid != "skip_reward":
            idx = int(cid.split("_")[1])
            self.run["deck"].append(self.choices[idx])
            
        if self.run["floor"] > 5:
            uid_str = str(self.user_id)
            spire_db[uid_str]["victories"] += 1
            spire_db[uid_str]["sector"] += 1
            spire_db[uid_str]["data_shards"] += 1
            clear_run(self.user_id)
            _save_db()
            
            win_embed = discord.Embed(title="RUN COMPLETE", description="You conquered the Megacorp Spire. Sector advanced.", color=THEME_CYAN)
            return await interaction.response.edit_message(embed=win_embed, view=None)

        _save_db()
        map_embed = discord.Embed(title="Navigation", description="Move to the next sector?", color=THEME_DARK_PURPLE)
        await interaction.response.edit_message(embed=map_embed, view=MapView(self.user_id, self.run))

class MapView(View):
    def __init__(self, user_id: int, run: Dict):
        super().__init__(timeout=600)
        self.user_id = user_id
        self.run = run
        
        btn = Button(label=f"Enter Floor {run['floor']}", style=ButtonStyle.danger)
        btn.callback = self.start_combat
        self.add_item(btn)

    async def start_combat(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("[DENIED] Unauthorized.", ephemeral=True)
            
        init_combat(self.run)
        _save_db()
        view = CombatView(self.user_id, self.run)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

class CharSelectView(View):
    def __init__(self, user_id: int):
        super().__init__(timeout=300)
        self.user_id = user_id
        for c_name in CLASSES.keys():
            btn = Button(label=c_name, style=ButtonStyle.primary)
            btn.custom_id = f"char_{c_name}"
            btn.callback = self.select_char
            self.add_item(btn)

    async def select_char(self, interaction: Interaction):
        if interaction.user.id != self.user_id: 
            return await interaction.response.send_message("[DENIED] Unauthorized.", ephemeral=True)
            
        char_name = interaction.data.get("custom_id", "").split("_")[1]
        
        spire_db[str(self.user_id)]["runs"] += 1
        run = create_run(str(self.user_id), char_name)
        init_combat(run)
        _save_db()
        
        view = CombatView(self.user_id, run)
        await interaction.response.edit_message(embed=view.build_embed(), view=view)

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

    @discord.slash_command(name="spire", description="Infiltrate the Megacorp Spire.")
    async def spire(self, ctx: discord.ApplicationContext):
        try:
            uid = str(ctx.author.id)
            player = init_player(uid)
            
            if player.get("active_run"):
                run = player["active_run"]
                if run.get("combat"):
                    view = CombatView(ctx.author.id, run)
                    await safe_reply(ctx, embed=view.build_embed(), view=view)
                else:
                    view = MapView(ctx.author.id, run)
                    map_embed = discord.Embed(title="Navigation", description="Resume infiltration.", color=THEME_DARK_PURPLE)
                    await safe_reply(ctx, embed=map_embed, view=view)
            else:
                sel_embed = discord.Embed(title="Select Your Operator", color=THEME_CYAN)
                for name, data in CLASSES.items():
                    sel_embed.add_field(
                        name=name, 
                        value=f"HP: {data['hp']}\n{data['desc']}", 
                        inline=False
                    )
                view = CharSelectView(ctx.author.id)
                await safe_reply(ctx, embed=sel_embed, view=view)
                
        except Exception as e:
            traceback.print_exc()
            await safe_reply(ctx, f"[ERR] Core Exception: {e}", ephemeral=True)

    @discord.slash_command(name="spire_abandon", description="Terminate your active run.")
    async def spire_abandon(self, ctx: discord.ApplicationContext):
        uid = str(ctx.author.id)
        if uid in spire_db and spire_db[uid].get("active_run"):
            clear_run(uid)
            await safe_reply(ctx, "Run terminated. Save cleared.")
        else:
            await safe_reply(ctx, "[DENIED] No active run found.", ephemeral=True)

    @discord.slash_command(name="spire_heist", description="Invade a target network and steal credits.")
    async def spire_heist(self, ctx: discord.ApplicationContext, target: Option(discord.Member, description="Target to hack.")):
        try:
            if ctx.author.id == target.id: 
                return await safe_reply(ctx, "[DENIED] Cannot target own network.", ephemeral=True)
            
            u1 = init_player(str(ctx.author.id))
            u2 = init_player(str(target.id))
            
            if u2["runs"] == 0 and u2["sector"] == 1:
                return await safe_reply(ctx, "[DENIED] Target IP inactive.", ephemeral=True)
            
            cp1 = (u1.get("sector", 1) * 10) + random.randint(1, 50)
            cp2 = (u2.get("sector", 1) * 10) + random.randint(1, 50)

            embed = discord.Embed(title="Net-Heist", color=THEME_PINK)
            if cp1 > cp2:
                stolen = int(u2["credits"] * 0.15)
                u2["credits"] -= stolen
                u1["credits"] += stolen + u2["bounty"]
                
                bounty_text = f"\nBounty Claimed: {u2['bounty']} CR" if u2["bounty"] > 0 else ""
                u2["bounty"] = 0
                u1["kills"] += 1
                u2["deaths"] += 1
                
                embed.description = f"{ctx.author.display_name} breached the firewall of {target.display_name}.\n\nStolen: {stolen} CR{bounty_text}"
                embed.color = THEME_HACK
            else:
                stolen = int(u1["credits"] * 0.15)
                u1["credits"] -= stolen
                u2["credits"] += stolen
                u2["kills"] += 1
                u1["deaths"] += 1
                
                embed.description = f"{ctx.author.display_name} was disconnected by the ICE of {target.display_name}.\n\nLost: {stolen} CR\nConnection severed."
                embed.color = THEME_PINK

            _save_db()
            await safe_reply(ctx, embed=embed)
        except Exception as e:
            await safe_reply(ctx, f"[ERR] Error: {e}", ephemeral=True)

    @discord.slash_command(name="spire_bounty", description="Place a hit on a rival.")
    async def spire_bounty(self, ctx: discord.ApplicationContext, target: Option(discord.Member, description="Target player"), amount: Option(int, description="Credits to place on bounty")):
        if amount <= 0: 
            return await safe_reply(ctx, "[DENIED] Must be > 0.", ephemeral=True)
        
        u1 = init_player(str(ctx.author.id))
        if u1["credits"] < amount: 
            return await safe_reply(ctx, "[DENIED] Insufficient funds.", ephemeral=True)
            
        u2 = init_player(str(target.id))
        u1["credits"] -= amount
        u2["bounty"] += amount
        _save_db()
        
        await safe_reply(ctx, embed=discord.Embed(title="Contract Issued", description=f"Bounty of {amount} CR placed on {target.display_name}.", color=THEME_CORP))

    @discord.slash_command(name="spire_board", description="View the Shadow-Net Leaderboard.")
    async def spire_board(self, ctx: discord.ApplicationContext):
        players = [(uid, data) for uid, data in spire_db.items() if isinstance(data, dict)]
        if not players: 
            return await safe_reply(ctx, "No data.", ephemeral=True)
        
        embed = discord.Embed(title="The Shadow-Net", color=THEME_CYAN)
        
        top_infil = sorted(players, key=lambda x: x[1].get("sector", 0), reverse=True)[:5]
        infil_str = "\n".join([f"<@{u}>: Sector {d.get('sector', 0)}" for u, d in top_infil]) or "None"
        
        top_hackers = sorted(players, key=lambda x: x[1].get("kills", 0), reverse=True)[:5]
        hackers_str = "\n".join([f"<@{u}>: {d.get('kills', 0)} Hacks" for u, d in top_hackers if d.get("kills", 0) > 0]) or "None"
        
        embed.add_field(name="Top Infiltrators", value=infil_str, inline=False)
        embed.add_field(name="Apex Hackers", value=hackers_str, inline=False)
        await safe_reply(ctx, embed=embed)

def setup(bot):
    bot.add_cog(SpireCog(bot))
