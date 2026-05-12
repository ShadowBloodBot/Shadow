# cogs/tower.py
import os
import json
import random
import uuid
import traceback
from pathlib import Path

import discord
from discord import Option, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Select
from discord.ext import commands

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
THEME_COMBAT = 0xE67E22 
THEME_GOLD = 0xFFD700 
THEME_BLOOD = 0x8A0303 # Dominance & Sacrifice

RARITY_COLORS = {
    "Common": 0x95A5A6, "Uncommon": 0x2ECC71, "Rare": 0x3498DB, 
    "Epic": 0x9B59B6, "Legendary": 0xE67E22, "Cursed": 0x8A0303
}
ITEM_SLOTS = ["Main Hand", "Off Hand", "Armor", "Accessory"]

# Psychological Escalation: Monsters evolve from pests to psychological terrors
MONSTERS = {
    1: ["Sewer Rat", "Slime Blob", "Wild Dog", "Desperate Mercenary", "Kobold Runt"],
    5: ["Goblin Scout", "Skeleton Warrior", "Corrupt Guard", "Giant Spider", "Orc Grunt"],
    15: ["Troll", "Ogre", "Gargoyle", "Vampire Spawn", "Cursed Armor", "Fallen Knight"],
    30: ["Lich", "Demon Soldier", "Shadow Stalker", "Bone Golem", "Hellhound", "Betrayer"],
    50: ["Void Walker", "Abyssal Horror", "Fallen Angel", "Dragon Whelp", "Void Titan"],
    80: ["Ego Fragment", "Aspect of Greed", "The Usurper", "Mind Flayer", "Arch-Demon"]
}

BIOMES = {
    "Sewers": {"range": (1, 20), "color": 0x2ECC71, "emoji": "🤢", "effect": "Toxic: 5% Poison Dmg every 5 turns."},
    "Catacombs": {"range": (21, 40), "color": 0x95A5A6, "emoji": "💀", "effect": "Darkness: 20% Miss Chance."},
    "Magma Core": {"range": (41, 60), "color": 0xE74C3C, "emoji": "🌋", "effect": "Heat: Skills cost 5 HP."},
    "The Abyss": {"range": (61, 80), "color": 0x8E44AD, "emoji": "🔮", "effect": "Despair: Healing reduced by 50%."},
    "Court of Shadows": {"range": (81, 999), "color": THEME_BLOOD, "emoji": "👑", "effect": "Absolute Power: Enemies have 20% execute chance."}
}

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

TOWER_STORE = (PERSIST_ROOT / "tower_v6.json")
tower_db = {}

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _save_tower(): _atomic_write(TOWER_STORE, tower_db)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

# --- LOGIC ---
def get_tower_data(user_id):
    uid = str(user_id)
    if uid not in tower_db:
        tower_db[uid] = {
            "floor": 1, "max_floor": 1, "hp": 100, "max_hp": 100, "gold": 0, "checkpoint": 1, "potions": 3,
            "class": "Warrior", "level": 1, "xp": 0, "stats": {"str": 5, "vit": 5, "agi": 5, "int": 5},
            "equipment": {"Main Hand": None, "Off Hand": None, "Armor": None, "Accessory": None},
            "inventory": [], "adrenaline": 0
        }
    
    # Non-destructive schema migration for Greene updates (PvP, Subjugation, Stakes)
    d = tower_db[uid]
    if "souls" not in d: d["souls"] = 0
    if "kills" not in d: d["kills"] = 0
    if "deaths" not in d: d["deaths"] = 0
    if "bounty" not in d: d["bounty"] = 0
    if "reputation" not in d: d["reputation"] = 0
    return d

def save_tower_data(user_id, data):
    tower_db[str(user_id)] = data
    _save_tower()

def get_total_stats(data):
    total = data["stats"].copy()
    for slot in ITEM_SLOTS:
        item = data["equipment"].get(slot)
        if item:
            for stat, val in item.get("stats", {}).items():
                total[stat] = total.get(stat, 0) + val
    total["atk"] = total["str"] * 2
    total["max_hp"] = 100 + (total["vit"] * 10)
    total["crit_chance"] = min(50, total["agi"] * 0.5)
    total["skill_dmg_mult"] = 1 + (total["int"] * 0.05)
    return total

def generate_rpg_item(floor, cursed=False):
    if cursed:
        rarity = "Cursed"
        budget = floor + 60
    else:
        rarity_roll = random.randint(1, 100)
        if rarity_roll > 98: rarity = "Legendary"
        elif rarity_roll > 85: rarity = "Epic"
        elif rarity_roll > 60: rarity = "Rare"
        elif rarity_roll > 30: rarity = "Uncommon"
        else: rarity = "Common"
        budget = floor + ({"Common": 2, "Uncommon": 5, "Rare": 10, "Epic": 20, "Legendary": 40}[rarity])
        
    slot = random.choice(ITEM_SLOTS)
    stats = {}
    possible_stats = ["str", "vit", "agi", "int"]
    num_stats = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 4, "Cursed": 4}[rarity]
    
    for _ in range(num_stats):
        s = random.choice(possible_stats)
        val = max(1, int(budget / num_stats))
        stats[s] = stats.get(s, 0) + val
        
    if cursed:
        # Cursed items give massive stats but sap vitality/health (Risk/Reward, Law 28)
        stats["vit"] = -abs(max(5, int(budget / 4))) 
        name = f"Cursed {slot} of the Usurper"
    else:
        name_prefix = {"str": "Might", "vit": "Health", "agi": "Swiftness", "int": "Wisdom"}
        dominant_stat = max(stats, key=stats.get)
        name = f"{rarity} {slot} of {name_prefix[dominant_stat]}"
        if rarity == "Legendary": name = f"The {random.choice(['God', 'Titan', 'Dragon', 'Void', 'Emperor'])}'s {slot}"

    return {"id": str(uuid.uuid4())[:8], "name": name, "rarity": rarity, "slot": slot, "stats": stats, "value": budget * 5}

def get_biome(floor):
    for name, data in BIOMES.items():
        if data["range"][0] <= floor <= data["range"][1]: return name, data
    return "Court of Shadows", BIOMES["Court of Shadows"]

def get_monster(floor):
    tiers = sorted(MONSTERS.keys()); sel = 1
    for t in tiers:
        if floor >= t: sel = t
    return random.choice(MONSTERS[sel])

def draw_bar(curr, max_val, color="🟩", length=10):
    if max_val <= 0: return color + "⬛" * 9
    pct = max(0, min(1, curr / max_val)); fill = int(pct * length)
    if fill == 0 and curr > 0: fill = 1 
    return color * fill + "⬜" * (length - fill)

# --- VIEWS ---
class LootDropView(View):
    def __init__(self, user, item):
        super().__init__(timeout=120)
        self.user = user; self.item = item; self.data = get_tower_data(user.id)
    @discord.ui.button(label="Take to Bag", style=ButtonStyle.success, emoji="🎒")
    async def take(self, button, interaction):
        if interaction.user.id != self.user.id: return
        self.data["inventory"].append(self.item)
        save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Resume Climbing", f"Looted **{self.item['name']}**."), view=view)
    @discord.ui.button(label="Salvage (Gold)", style=ButtonStyle.secondary, emoji="💰")
    async def salvage(self, button, interaction):
        if interaction.user.id != self.user.id: return
        val = self.item["value"]; self.data["gold"] += val
        save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Resume Climbing", f"Salvaged for **{val} Gold**."), view=view)

class DarkAltarView(View):
    def __init__(self, user):
        super().__init__(timeout=120)
        self.user = user; self.data = get_tower_data(user.id)
        
    @discord.ui.button(label="Bleed for Power (-10 Vit, +3 All)", style=ButtonStyle.danger, emoji="🩸")
    async def sacrifice_health(self, button, interaction):
        if interaction.user.id != self.user.id: return
        self.data["stats"]["vit"] = max(1, self.data["stats"]["vit"] - 10)
        for s in ["str", "agi", "int"]: self.data["stats"][s] += 3
        self.data["hp"] = min(self.data["hp"], get_total_stats(self.data)["max_hp"])
        save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("The Pact is Sealed", "Your vitality drains, but power surges through you. Power is not given; it is taken."), view=view)

    @discord.ui.button(label="Gamble Soul (20% Curse, 80% Legendary)", style=ButtonStyle.primary, emoji="🔮")
    async def gamble_soul(self, button, interaction):
        if interaction.user.id != self.user.id: return
        roll = random.randint(1, 100)
        if roll <= 20:
            item = generate_rpg_item(self.data["floor"], cursed=True)
            msg = "The altar rejects your weakness. You are cursed."
        else:
            item = generate_rpg_item(self.data["floor"] + 20)
            item["rarity"] = "Legendary"
            msg = "Fortune favors the bold. The altar yields."
            
        self.data["inventory"].append(item)
        save_tower_data(self.user.id, self.data)
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Altar Yields", f"{msg}\nReceived **{item['name']}**."), view=view)

    @discord.ui.button(label="Walk Away", style=ButtonStyle.secondary, emoji="🚶")
    async def walk_away(self, button, interaction):
        if interaction.user.id != self.user.id: return
        view = TowerGameView(self.user)
        await interaction.response.edit_message(embed=view.update_embed("Exploration", "You leave the altar untouched. Survival over greed."), view=view)

class TowerGameView(View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user; self.user_id = str(user.id)
        self.data = get_tower_data(user.id)
        self.stats = get_total_stats(self.data)
        self.mode = "EXPLORE" ; self.enemy = None; self.combat_log = []
        self.data["hp"] = min(self.data["hp"], self.stats["max_hp"])
        self.render_main_menu()

    def get_inventory_embed(self):
        stats = get_total_stats(self.data)
        embed = discord.Embed(title=f"🎒 {self.user.display_name}'s Vault", color=THEME_PRIMARY)
        
        s_text = (
            f"❤️ **HP:** {self.data['hp']}/{stats['max_hp']}\n"
            f"⚔️ **ATK:** {stats['atk']} (Str: {stats['str']})\n"
            f"🛡️ **DEF:** {stats['vit'] // 2} (Vit: {stats['vit']})\n"
            f"⚡ **CRIT:** {stats['crit_chance']}% (Agi: {stats['agi']})\n"
            f"💀 **Souls:** {self.data.get('souls', 0)} | 👑 **Kills:** {self.data.get('kills', 0)}"
        )
        embed.add_field(name="📊 Attributes of Power", value=s_text, inline=True)
        
        g_text = ""
        for slot in ITEM_SLOTS:
            item = self.data["equipment"].get(slot)
            if item:
                stats_str = " ".join([f"**{k.upper()}**+{v}" for k,v in item['stats'].items()])
                g_text += f"**{slot}:** {item['name']} ({stats_str})\n"
            else: 
                g_text += f"**{slot}:** Empty\n"
        embed.add_field(name="🛡️ Armament", value=g_text, inline=False)
        
        i_text = f"Items: {len(self.data['inventory'])}"
        if not self.data["inventory"]: 
            i_text += "\n(Empty)"
        else:
            for item in self.data["inventory"][:5]: 
                i_text += f"\n• {item['name']}"
            if len(self.data['inventory']) > 5: 
                i_text += "\n...and more."
                
        embed.add_field(name="🎒 Backpack", value=i_text, inline=False)
        return embed

    def get_shop_embed(self):
        embed = discord.Embed(title="⛺ The Black Market", description="Sanctuary is an illusion. Rest while you can afford it.", color=THEME_GOLD)
        embed.add_field(name="Reserves", value=f"💰 {self.data['gold']} Gold\n👻 {self.data.get('souls', 0)} Souls")
        embed.add_field(name="Potions", value=f"🧪 {self.data['potions']}")
        embed.add_field(name="Bounty on Head", value=f"🎯 {self.data.get('bounty', 0)} Gold")
        return embed

    def update_embed(self, title, desc, color=THEME_PRIMARY):
        if self.mode == "INVENTORY": return self.get_inventory_embed()
        elif self.mode == "SHOP": return self.get_shop_embed()

        b_name, b_data = get_biome(self.data['floor'])
        p_bar = draw_bar(self.data["hp"], self.stats["max_hp"], "🟩")
        a_bar = draw_bar(self.data.get("adrenaline", 0), 100, "🟨", 8)
        
        final_color = b_data["color"] if self.mode != "COMBAT" else THEME_COMBAT
        embed = discord.Embed(
            title=f"{b_data['emoji']} {title} | Floor {self.data['floor']}", 
            description=desc, 
            color=final_color
        )
        
        if self.mode == "COMBAT" and self.enemy:
            e_bar = draw_bar(self.enemy['hp'], self.enemy['max_hp'], "🟥")
            intent = self.enemy.get("intent", "Unknown")
            embed.add_field(
                name=f"🆚 {self.enemy['name']}", 
                value=f"{e_bar} {self.enemy['hp']} HP\n⚠️ **Intent:** {intent}", 
                inline=False
            )
            if self.combat_log: 
                log_text = "\n".join(self.combat_log[-6:])
                embed.add_field(name="📜 Combat Log", value=f"```ansi\n{log_text}\n
```", inline=False)

        stats_disp = f"⚔️{self.stats['atk']} 🛡️{self.stats['vit']//2} 💰{self.data['gold']}"
        embed.add_field(
            name=f"👤 {self.user.display_name} (Lvl {self.data['level']})", 
            value=f"{p_bar} {self.data['hp']} HP\n{a_bar} Limit Break\n{stats_disp}", 
            inline=False
        )
        embed.set_footer(text=f"{b_name}: {b_data['effect']} | Power respects only power.")
        return embed

    def render_main_menu(self):
        self.clear_items()
        if self.mode == "COMBAT":
            atk_btn = Button(label="Strike", style=ButtonStyle.danger, emoji="⚔️", row=0)
            atk_btn.callback = lambda i: self.wrapper(i, "act_atk")
            self.add_item(atk_btn)
            
            def_btn = Button(label="Guard", style=ButtonStyle.secondary, emoji="🛡️", row=0)
            def_btn.callback = lambda i: self.wrapper(i, "act_def")
            self.add_item(def_btn)
            
            if self.data["potions"] > 0:
                pot_btn = Button(label=f"Elixir ({self.data['potions']})", style=ButtonStyle.success, emoji="🧪", row=0)
                pot_btn.callback = lambda i: self.wrapper(i, "act_pot")
                self.add_item(pot_btn)
                
            if self.data["adrenaline"] >= 100:
                ult_btn = Button(label="EXECUTE", style=ButtonStyle.primary, emoji="⚡", row=1)
                ult_btn.callback = lambda i: self.wrapper(i, "act_ult")
                self.add_item(ult_btn)
                
        elif self.mode == "EXPLORE":
            climb_btn = Button(label="Ascend", style=ButtonStyle.success, emoji="🧗", row=0)
            climb_btn.callback = lambda i: self.wrapper(i, "nav_climb")
            self.add_item(climb_btn)
            
            rest_btn = Button(label="Camp (100g)", style=ButtonStyle.primary, emoji="💤", row=0)
            rest_btn.callback = lambda i: self.wrapper(i, "nav_rest")
            self.add_item(rest_btn)
            
            gear_btn = Button(label="Vault", style=ButtonStyle.secondary, emoji="🎒", row=1)
            gear_btn.callback = lambda i: self.wrapper(i, "nav_gear")
            self.add_item(gear_btn)
            
        elif self.mode == "INVENTORY":
            if self.data["inventory"]:
                options = []
                for item in self.data["inventory"][:25]:
                    s_str = ", ".join([f"{k.upper()}+{v}" for k,v in item["stats"].items()])
                    options.append(SelectOption(label=f"{item['name']} ({item['slot']})", description=s_str, value=item["id"]))
                select = Select(placeholder="Equip Item...", options=options, row=0)
                select.callback = self.equip_callback
                self.add_item(select)
                
            back_btn = Button(label="Return", style=ButtonStyle.secondary, emoji="↩️", row=1)
            back_btn.callback = lambda i: self.wrapper(i, "nav_back")
            self.add_item(back_btn)
            
        elif self.mode == "SHOP":
            buy_btn = Button(label="Buy Elixir (50g)", style=ButtonStyle.success, emoji="🧪", row=0)
            buy_btn.callback = lambda i: self.wrapper(i, "shop_buy")
            self.add_item(buy_btn)
            
            sell_btn = Button(label="Liquidate Assets", style=ButtonStyle.danger, emoji="💰", row=0)
            sell_btn.callback = lambda i: self.wrapper(i, "shop_sell")
            self.add_item(sell_btn)

            leave_btn = Button(label="Depart", style=ButtonStyle.secondary, emoji="👋", row=1)
            leave_btn.callback = lambda i: self.wrapper(i, "shop_leave")
            self.add_item(leave_btn)

    async def equip_callback(self, interaction):
        if interaction.user.id != self.user.id: return
        await interaction.response.defer() 
        val = interaction.data["values"][0]
        to_equip = next((i for i in self.data["inventory"] if i["id"] == val), None)
        if to_equip:
            slot = to_equip["slot"]; current = self.data["equipment"].get(slot)
            if current: self.data["inventory"].append(current)
            self.data["equipment"][slot] = to_equip; self.data["inventory"].remove(to_equip)
            save_tower_data(self.user.id, self.data); self.stats = get_total_stats(self.data) 
            self.render_main_menu() 
            await interaction.edit_original_response(embed=self.update_embed("Arsenal Updated", "Always arm yourself against betrayal."), view=self)

    async def wrapper(self, interaction, cid):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 This is not your domain.", ephemeral=True)
        try:
            await interaction.response.defer()
            if "act_" in cid: await self.resolve_combat(interaction, cid)
            elif cid == "nav_gear":
                self.mode = "INVENTORY"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("The Vault", "Take stock of your leverage."), view=self)
            elif cid == "nav_back":
                self.mode = "EXPLORE"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Ascension", "The climb continues."), view=self)
            elif "shop_" in cid: await self.resolve_shop(interaction, cid)
            else: await self.resolve_nav(interaction, cid)
        except Exception as e: traceback.print_exc()

    async def resolve_shop(self, interaction, cid):
        if cid == "shop_buy":
            if self.data["gold"] >= 50:
                self.data["gold"] -= 50; self.data["potions"] += 1; save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("Black Market", "Elixir acquired. A necessary dependency."), view=self)
            else: await interaction.followup.send("❌ Your poverty offends them. Need 50 Gold.", ephemeral=True)
        elif cid == "shop_sell":
            total = sum([i["value"] for i in self.data["inventory"]]); count = len(self.data["inventory"])
            self.data["inventory"] = []; self.data["gold"] += total; save_tower_data(self.user.id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Black Market", f"Liquidated {count} assets for {total}g. Wealth is leverage."), view=self)
        elif cid == "shop_leave":
            self.mode = "EXPLORE"; self.data["floor"] += 1; self.render_main_menu()
            await interaction.edit_original_response(embed=self.update_embed("Ascension", "You leave the false safety of the camp behind."), view=self)

    async def resolve_nav(self, interaction, cid):
        if cid == "nav_rest":
            if self.data["gold"] >= 100:
                self.data["gold"] -= 100; self.data["hp"] = self.stats["max_hp"]; save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("💤 Rested", "HP Restored. Do not let your guard down."), view=self)
            else: await interaction.followup.send("❌ Need 100 Gold.", ephemeral=True)
        elif cid == "nav_climb":
            if self.data["floor"] % 5 == 0 and self.data["floor"] > 1:
                self.mode = "SHOP"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Black Market", "A neutral zone. Trust no one here."), view=self)
                return
            roll = random.randint(1, 100)
            if roll <= 10:
                view = DarkAltarView(self.user)
                embed = discord.Embed(title="🩸 Dark Altar Encountered", description="A monolith pulses with forbidden energy. Law 28: Enter action with boldness. What will you sacrifice?", color=THEME_BLOOD)
                await interaction.edit_original_response(embed=embed, view=view)
            elif roll <= 40: 
                item = generate_rpg_item(self.data["floor"]); view = LootDropView(self.user, item)
                stats_str = "\n".join([f"• **{k.upper()}:** +{v}" for k,v in item['stats'].items()])
                
                desc = (
                    f"A forgotten stash.\n\n"
                    f"**{item['name']}**\n"
                    f"{stats_str}\n\n"
                    f"*Market Value: {item['value']} Gold*"
                )
                embed = discord.Embed(title="🎁 Asset Seized", description=desc, color=RARITY_COLORS.get(item['rarity'], 0xFFFFFF))
                await interaction.edit_original_response(embed=embed, view=view)
            else: 
                self.start_combat(); await interaction.edit_original_response(embed=self.update_embed("⚔️ Conflict Initiated", "Show no mercy. Law 15: Crush your enemy totally."), view=self)

    def start_combat(self):
        self.mode = "COMBAT"; floor = self.data["floor"]; name = get_monster(floor)
        hp = (floor * 25) + 80; power = (floor * 3) + 5
        self.enemy = {"name": name, "hp": hp, "max_hp": hp, "power": power, "intent": random.choice(["Strike", "Heavy Strike"])}
        self.combat_log = [f"⚔️ {name} blocks your path!"]; self.render_main_menu()

    async def resolve_combat(self, interaction, action):
        if not self.enemy: return
        p_dmg, p_block = 0, 0
        if action == "act_atk":
            dmg = self.stats["atk"] + random.randint(-2, 2)
            if random.randint(1, 100) <= self.stats["crit_chance"]: dmg = int(dmg * 1.5); self.combat_log.append(f"💥 CRITICAL EXECUTION! {dmg} dmg.")
            else: self.combat_log.append(f"🗡️ Strike lands: {dmg} dmg.")
            p_dmg = dmg; self.data["adrenaline"] = min(100, self.data["adrenaline"] + 10)
        elif action == "act_def":
            p_block = self.stats["vit"]; self.combat_log.append(f"🛡️ Guard raised. Mitigating {p_block}.")
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 5)
        elif action == "act_ult":
            p_dmg = self.stats["atk"] * 3; self.combat_log.append(f"⚡ ABSOLUTE DOMINANCE! {p_dmg} DMG!")
            self.data["adrenaline"] = 0
        elif action == "act_pot":
            heal = 50 + (self.stats["int"] * 2); self.data["hp"] = min(self.stats["max_hp"], self.data["hp"] + heal)
            self.data["potions"] -= 1; self.combat_log.append(f"🧪 Restored +{heal} HP.")

        self.enemy["hp"] -= p_dmg
        if self.enemy["hp"] > 0:
            e_dmg = self.enemy["power"]
            if self.enemy["intent"] == "Heavy Strike": e_dmg = int(e_dmg * 1.5)
            mitigation = (self.stats["vit"] // 3) + p_block
            final_dmg = max(0, e_dmg - mitigation)
            self.data["hp"] -= final_dmg
            self.combat_log.append(f"👾 {self.enemy['name']} strikes for {final_dmg} (Mitigated {mitigation}).")
            self.enemy["intent"] = random.choice(["Strike", "Heavy Strike", "Defend"])
        
        if self.enemy["hp"] <= 0:
            xp_gain = 20 + self.data["floor"]; gold_gain = 10 + (self.data["floor"] * 2)
            soul_gain = 1 if self.data["floor"] > 10 else 0
            
            self.data["xp"] += xp_gain; self.data["gold"] += gold_gain; self.data["floor"] += 1
            if soul_gain: self.data["souls"] += soul_gain
            
            self.mode = "EXPLORE"; self.enemy = None; req = self.data["level"] * 100
            if self.data["xp"] >= req:
                self.data["xp"] -= req; self.data["level"] += 1
                self.data["stats"]["str"] += 1; self.data["stats"]["vit"] += 1
                self.combat_log.append("✨ ELEVATION! Stats Increased.")
                
            save_tower_data(self.user_id, self.data); self.render_main_menu()
            soul_str = f" | +{soul_gain} Souls" if soul_gain else ""
            await interaction.edit_original_response(embed=self.update_embed("Target Eliminated", f"Obstacle removed.\n+{xp_gain} XP | +{gold_gain} Gold{soul_str}"), view=self)
        elif self.data["hp"] <= 0:
            self.data["hp"] = 0; lost_gold = int(self.data["gold"] / 2)
            self.data["gold"] -= lost_gold; self.data["floor"] = max(1, self.data["floor"] - 5)
            self.data["deaths"] += 1
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("💀 Broken", f"You showed weakness and paid the price.\nLost {lost_gold} Gold.\nFloor reduced."), view=None)
        else:
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Conflict", "Maintain control..."), view=self)

# --- COG SETUP ---
class TowerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        global tower_db
        if TOWER_STORE.exists():
            try: tower_db = json.loads(TOWER_STORE.read_text())
            except: tower_db = {}
        else: tower_db = {}

    @discord.slash_command(name="tower", description="Enter the Shadow Tower. Ascend or break.")
    async def tower(self, ctx):
        view = TowerGameView(ctx.author)
        embed = view.update_embed("The Shadow Tower", "You cross the threshold. There is no retreat, only leverage and power.")
        await safe_reply(ctx, embed=embed, view=view)

    @discord.slash_command(name="tower_duel", description="Crush a rival. Steal their gold. Claim their souls.")
    async def tower_duel(self, ctx, target: Option(discord.Member, "The rival you wish to crush.")):
        if ctx.author.id == target.id: return await safe_reply(ctx, "❌ Self-destruction is not a strategy.", ephemeral=True)
        
        u1_data = get_tower_data(ctx.author.id)
        if str(target.id) not in tower_db: return await safe_reply(ctx, "❌ This target is entirely irrelevant (Not in database).", ephemeral=True)
        u2_data = get_tower_data(target.id)

        s1 = get_total_stats(u1_data); s2 = get_total_stats(u2_data)
        
        # Combat Power Rating Calculation
        cp1 = s1["atk"] + s1["vit"] + s1["max_hp"] + (s1["crit_chance"] * 2)
        cp2 = s2["atk"] + s2["vit"] + s2["max_hp"] + (s2["crit_chance"] * 2)
        
        # Add 15% RNG Variance to mimic chaos of war
        cp1_final = cp1 * random.uniform(0.85, 1.15)
        cp2_final = cp2 * random.uniform(0.85, 1.15)

        embed = discord.Embed(title="⚔️ Court of Shadows: Duel", color=THEME_BLOOD)
        
        if cp1_final > cp2_final:
            stolen_gold = int(u2_data["gold"] * 0.15) # Steal 15% of their gold
            bounty_claim = u2_data["bounty"]
            u2_data["gold"] -= stolen_gold
            u1_data["gold"] += (stolen_gold + bounty_claim)
            u2_data["bounty"] = 0
            u1_data["kills"] += 1; u2_data["deaths"] += 1
            u1_data["souls"] += 5
            
            bounty_str = f"\n🎯 **Claimed Bounty:** {bounty_claim} Gold" if bounty_claim > 0 else ""
            desc = f"**{ctx.author.display_name}** established absolute dominance over **{target.display_name}**.\nLaw 15: Crush your enemy totally.\n\n💰 **Plundered:** {stolen_gold} Gold{bounty_str}\n💀 **Gained:** 5 Souls"
            embed.color = THEME_WIN
        else:
            stolen_gold = int(u1_data["gold"] * 0.15)
            u1_data["gold"] -= stolen_gold
            u2_data["gold"] += stolen_gold
            u2_data["kills"] += 1; u1_data["deaths"] += 1
            u2_data["souls"] += 5
            
            desc = f"**{ctx.author.display_name}** overestimated their leverage. **{target.display_name}** repelled the assault.\n\n💰 **Lost:** {stolen_gold} Gold\n💀 You have proven your weakness."
            embed.color = THEME_LOSS

        save_tower_data(ctx.author.id, u1_data)
        save_tower_data(target.id, u2_data)
        
        embed.description = desc
        await safe_reply(ctx, embed=embed)

    @discord.slash_command(name="tower_bounty", description="Place a price on a rival's head using your own gold.")
    async def tower_bounty(self, ctx, target: Option(discord.Member, "The rival to mark."), amount: Option(int, "Gold to place on their head.")):
        if amount <= 0: return await safe_reply(ctx, "❌ Poverty is not intimidating.", ephemeral=True)
        if ctx.author.id == target.id: return await safe_reply(ctx, "❌ Attention seeking is a weakness.", ephemeral=True)
        
        u1_data = get_tower_data(ctx.author.id)
        if u1_data["gold"] < amount: return await safe_reply(ctx, "❌ You lack the capital to back this threat.", ephemeral=True)
        
        if str(target.id) not in tower_db: return await safe_reply(ctx, "❌ Target does not exist in the Tower.", ephemeral=True)
        u2_data = get_tower_data(target.id)
        
        u1_data["gold"] -= amount
        u2_data["bounty"] += amount
        save_tower_data(ctx.author.id, u1_data)
        save_tower_data(target.id, u2_data)
        
        embed = discord.Embed(title="🎯 Vendetta Declared", description=f"**{ctx.author.display_name}** has placed a bounty of **{amount} Gold** on the head of **{target.display_name}**.\n\nTotal Bounty on Target: **{u2_data['bounty']} Gold**.\n*Law 3: Conceal your intentions. Let others do your dirty work.*", color=THEME_GOLD)
        await safe_reply(ctx, embed=embed)

    @discord.slash_command(name="tower_hierarchy", description="View the Court of Shadows (Leaderboard)")
    async def tower_hierarchy(self, ctx):
        if not tower_db: return await safe_reply(ctx, "The Tower is empty.", ephemeral=True)
        
        players = [(uid, data) for uid, data in tower_db.items() if isinstance(data, dict) and "floor" in data]
        if not players: return await safe_reply(ctx, "No data.", ephemeral=True)
        
        # Sort by Floor
        top_climbers = sorted(players, key=lambda x: x[1].get("floor", 0), reverse=True)[:5]
        # Sort by Kills
        top_killers = sorted(players, key=lambda x: x[1].get("kills", 0), reverse=True)[:5]
        # Sort by Bounties
        top_wanted = sorted(players, key=lambda x: x[1].get("bounty", 0), reverse=True)[:3]
        
        embed = discord.Embed(title="👑 The Court of Shadows", description="Status is the only currency that matters.", color=THEME_BLOOD)
        
        c_text = "\n".join([f"<@{uid}>: Floor {d.get('floor', 0)}" for uid, d in top_climbers])
        embed.add_field(name="🧗 Highest Ascensions", value=c_text or "None", inline=False)
        
        k_text = "\n".join([f"<@{uid}>: {d.get('kills', 0)} Kills" for uid, d in top_killers if d.get('kills', 0) > 0])
        embed.add_field(name="💀 Apex Predators", value=k_text or "None", inline=False)
        
        w_text = "\n".join([f"<@{uid}>: {d.get('bounty', 0)} Gold" for uid, d in top_wanted if d.get('bounty', 0) > 0])
        if w_text: embed.add_field(name="🎯 Most Wanted", value=w_text, inline=False)
        
        await safe_reply(ctx, embed=embed)

def setup(bot):
    bot.add_cog(TowerCog(bot))
