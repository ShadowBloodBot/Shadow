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

RARITY_COLORS = {
    "Common": 0x95A5A6, "Uncommon": 0x2ECC71, "Rare": 0x3498DB, 
    "Epic": 0x9B59B6, "Legendary": 0xE67E22
}
ITEM_SLOTS = ["Main Hand", "Off Hand", "Armor", "Accessory"]
MONSTERS = {
    1: ["Sewer Rat", "Slime Blob", "Wild Dog", "Angry Bat", "Kobold Runt"],
    5: ["Goblin Scout", "Skeleton Warrior", "Bandit", "Giant Spider", "Orc Grunt"],
    15: ["Troll", "Ogre", "Gargoyle", "Vampire Spawn", "Cursed Armor", "Dark Elf"],
    30: ["Lich", "Demon Soldier", "Shadow Stalker", "Bone Golem", "Hellhound"],
    50: ["Void Walker", "Abyssal Horror", "Fallen Angel", "Dragon Whelp", "Void Titan"]
}
BIOMES = {
    "Sewers": {"range": (1, 20), "color": 0x2ECC71, "emoji": "🤢", "effect": "Toxic: 5% Poison Dmg every 5 turns."},
    "Catacombs": {"range": (21, 40), "color": 0x95A5A6, "emoji": "💀", "effect": "Darkness: 20% Miss Chance."},
    "Magma Core": {"range": (41, 60), "color": 0xE74C3C, "emoji": "🌋", "effect": "Heat: Skills cost 5 HP."},
    "Void": {"range": (61, 999), "color": 0x8E44AD, "emoji": "🔮", "effect": "Void: Enemies deal True Damage."}
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
    return tower_db[uid]

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

def generate_rpg_item(floor):
    rarity_roll = random.randint(1, 100)
    if rarity_roll > 98: rarity = "Legendary"
    elif rarity_roll > 85: rarity = "Epic"
    elif rarity_roll > 60: rarity = "Rare"
    elif rarity_roll > 30: rarity = "Uncommon"
    else: rarity = "Common"
    
    slot = random.choice(ITEM_SLOTS)
    budget = floor + ({"Common": 2, "Uncommon": 5, "Rare": 10, "Epic": 20, "Legendary": 40}[rarity])
    stats = {}
    possible_stats = ["str", "vit", "agi", "int"]
    num_stats = {"Common": 1, "Uncommon": 2, "Rare": 3, "Epic": 4, "Legendary": 4}[rarity]
    
    for _ in range(num_stats):
        s = random.choice(possible_stats)
        val = max(1, int(budget / num_stats))
        stats[s] = stats.get(s, 0) + val
        
    name_prefix = {"str": "Might", "vit": "Health", "agi": "Swiftness", "int": "Wisdom"}
    dominant_stat = max(stats, key=stats.get)
    name = f"{rarity} {slot} of {name_prefix[dominant_stat]}"
    if rarity == "Legendary": name = f"The {random.choice(['God', 'Titan', 'Dragon', 'Void'])}'s {slot}"

    return {"id": str(uuid.uuid4())[:8], "name": name, "rarity": rarity, "slot": slot, "stats": stats, "value": budget * 5}

def get_biome(floor):
    for name, data in BIOMES.items():
        if data["range"][0] <= floor <= data["range"][1]: return name, data
    return "Void", BIOMES["Void"]

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
        embed = discord.Embed(title=f"🎒 {self.user.display_name}'s Gear", color=THEME_PRIMARY)
        
        # Safely formatted string
        s_text = (
            f"❤️ **HP:** {self.data['hp']}/{stats['max_hp']}\n"
            f"⚔️ **ATK:** {stats['atk']} (Str: {stats['str']})\n"
            f"🛡️ **DEF:** {stats['vit'] // 2} (Vit: {stats['vit']})\n"
            f"⚡ **CRIT:** {stats['crit_chance']}% (Agi: {stats['agi']})"
        )
        embed.add_field(name="📊 Stats", value=s_text, inline=True)
        
        g_text = ""
        for slot in ITEM_SLOTS:
            item = self.data["equipment"].get(slot)
            if item:
                stats_str = " ".join([f"**{k.upper()}**+{v}" for k,v in item['stats'].items()])
                g_text += f"**{slot}:** {item['name']} ({stats_str})\n"
            else: 
                g_text += f"**{slot}:** Empty\n"
        embed.add_field(name="🛡️ Equipment", value=g_text, inline=False)
        
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
        embed = discord.Embed(title="⛺ Safe Zone Merchant", description="Stay a while and listen.", color=THEME_GOLD)
        embed.add_field(name="Your Gold", value=f"💰 {self.data['gold']}")
        embed.add_field(name="Potions", value=f"🧪 {self.data['potions']}")
        embed.add_field(name="Inventory Value", value=f"💎 {sum([i['value'] for i in self.data['inventory']])}g")
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
                embed.add_field(name="📜 Combat Log", value=f"```ansi\n{log_text}\n```", inline=False)

        stats_disp = f"⚔️{self.stats['atk']} 🛡️{self.stats['vit']//2} 💰{self.data['gold']}"
        embed.add_field(
            name=f"👤 {self.user.display_name} (Lvl {self.data['level']})", 
            value=f"{p_bar} {self.data['hp']} HP\n{a_bar} Limit Break\n{stats_disp}", 
            inline=False
        )
        embed.set_footer(text=f"{b_name}: {b_data['effect']}")
        return embed

    def render_main_menu(self):
        self.clear_items()
        if self.mode == "COMBAT":
            atk_btn = Button(label="Attack", style=ButtonStyle.danger, emoji="⚔️", row=0)
            atk_btn.callback = lambda i: self.wrapper(i, "act_atk")
            self.add_item(atk_btn)
            
            def_btn = Button(label="Defend", style=ButtonStyle.secondary, emoji="🛡️", row=0)
            def_btn.callback = lambda i: self.wrapper(i, "act_def")
            self.add_item(def_btn)
            
            if self.data["potions"] > 0:
                pot_btn = Button(label=f"Potion ({self.data['potions']})", style=ButtonStyle.success, emoji="🧪", row=0)
                pot_btn.callback = lambda i: self.wrapper(i, "act_pot")
                self.add_item(pot_btn)
                
            if self.data["adrenaline"] >= 100:
                ult_btn = Button(label="LIMIT BREAK", style=ButtonStyle.primary, emoji="⚡", row=1)
                ult_btn.callback = lambda i: self.wrapper(i, "act_ult")
                self.add_item(ult_btn)
                
        elif self.mode == "EXPLORE":
            climb_btn = Button(label="Climb", style=ButtonStyle.success, emoji="🧗", row=0)
            climb_btn.callback = lambda i: self.wrapper(i, "nav_climb")
            self.add_item(climb_btn)
            
            rest_btn = Button(label="Rest (100g)", style=ButtonStyle.primary, emoji="💤", row=0)
            rest_btn.callback = lambda i: self.wrapper(i, "nav_rest")
            self.add_item(rest_btn)
            
            gear_btn = Button(label="Bag/Gear", style=ButtonStyle.secondary, emoji="🎒", row=1)
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
                
            back_btn = Button(label="Back to Game", style=ButtonStyle.secondary, emoji="↩️", row=1)
            back_btn.callback = lambda i: self.wrapper(i, "nav_back")
            self.add_item(back_btn)
            
        elif self.mode == "SHOP":
            buy_btn = Button(label="Buy Potion (50g)", style=ButtonStyle.success, emoji="🧪", row=0)
            buy_btn.callback = lambda i: self.wrapper(i, "shop_buy")
            self.add_item(buy_btn)
            
            sell_btn = Button(label="Sell Junk", style=ButtonStyle.danger, emoji="💰", row=0)
            sell_btn.callback = lambda i: self.wrapper(i, "shop_sell")
            self.add_item(sell_btn)
            
            leave_btn = Button(label="Leave Shop", style=ButtonStyle.secondary, emoji="👋", row=1)
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
            await interaction.edit_original_response(embed=self.update_embed("Gear Updated", ""), view=self)

    async def wrapper(self, interaction, cid):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 Not your session.", ephemeral=True)
        try:
            await interaction.response.defer()
            if "act_" in cid: await self.resolve_combat(interaction, cid)
            elif cid == "nav_gear":
                self.mode = "INVENTORY"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Inventory", ""), view=self)
            elif cid == "nav_back":
                self.mode = "EXPLORE"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Exploration", "Back to the tower."), view=self)
            elif "shop_" in cid: await self.resolve_shop(interaction, cid)
            else: await self.resolve_nav(interaction, cid)
        except Exception as e: traceback.print_exc()

    async def resolve_shop(self, interaction, cid):
        if cid == "shop_buy":
            if self.data["gold"] >= 50:
                self.data["gold"] -= 50; self.data["potions"] += 1; save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("Shop", "Bought potion."), view=self)
            else: await interaction.followup.send("❌ Not enough gold.", ephemeral=True)
        elif cid == "shop_sell":
            total = sum([i["value"] for i in self.data["inventory"]]); count = len(self.data["inventory"])
            self.data["inventory"] = []; self.data["gold"] += total; save_tower_data(self.user.id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Shop", f"Sold {count} items for {total}g."), view=self)
        elif cid == "shop_leave":
            self.mode = "EXPLORE"; self.data["floor"] += 1; self.render_main_menu()
            await interaction.edit_original_response(embed=self.update_embed("Exploration", "Moving on..."), view=self)

    async def resolve_nav(self, interaction, cid):
        if cid == "nav_rest":
            if self.data["gold"] >= 100:
                self.data["gold"] -= 100; self.data["hp"] = self.stats["max_hp"]; save_tower_data(self.user.id, self.data)
                await interaction.edit_original_response(embed=self.update_embed("💤 Rested", "HP Fully Restored."), view=self)
            else: await interaction.followup.send("❌ Need 100 Gold.", ephemeral=True)
        elif cid == "nav_climb":
            if self.data["floor"] % 5 == 0 and self.data["floor"] > 1:
                self.mode = "SHOP"; self.render_main_menu()
                await interaction.edit_original_response(embed=self.update_embed("Shop", "Safe zone reached."), view=self)
                return
            roll = random.randint(1, 100)
            if roll <= 30: 
                item = generate_rpg_item(self.data["floor"]); view = LootDropView(self.user, item)
                stats_str = "\n".join([f"• **{k.upper()}:** +{v}" for k,v in item['stats'].items()])
                
                desc = (
                    f"You found a chest!\n\n"
                    f"**{item['name']}**\n"
                    f"{stats_str}\n\n"
                    f"*Value: {item['value']} Gold*"
                )
                
                embed = discord.Embed(title="🎁 Treasure Found!", description=desc, color=RARITY_COLORS.get(item['rarity'], 0xFFFFFF))
                await interaction.edit_original_response(embed=embed, view=view)
            else: 
                self.start_combat(); await interaction.edit_original_response(embed=self.update_embed("⚔️ Encounter!", "Prepare yourself!"), view=self)

    def start_combat(self):
        self.mode = "COMBAT"; floor = self.data["floor"]; name = get_monster(floor)
        hp = (floor * 25) + 80; power = (floor * 3) + 5
        self.enemy = {"name": name, "hp": hp, "max_hp": hp, "power": power, "intent": random.choice(["Attack", "Heavy Attack"])}
        self.combat_log = [f"⚔️ Encountered {name}!"]; self.render_main_menu()

    async def resolve_combat(self, interaction, action):
        if not self.enemy: return
        p_dmg, p_block = 0, 0
        if action == "act_atk":
            dmg = self.stats["atk"] + random.randint(-2, 2)
            if random.randint(1, 100) <= self.stats["crit_chance"]: dmg = int(dmg * 1.5); self.combat_log.append(f"💥 CRIT! You deal {dmg} dmg.")
            else: self.combat_log.append(f"🗡️ You deal {dmg} dmg.")
            p_dmg = dmg; self.data["adrenaline"] = min(100, self.data["adrenaline"] + 10)
        elif action == "act_def":
            p_block = self.stats["vit"]; self.combat_log.append(f"🛡️ Block raised ({p_block}).")
            self.data["adrenaline"] = min(100, self.data["adrenaline"] + 5)
        elif action == "act_ult":
            p_dmg = self.stats["atk"] * 3; self.combat_log.append(f"⚡ LIMIT BREAK! {p_dmg} DMG!")
            self.data["adrenaline"] = 0
        elif action == "act_pot":
            heal = 50 + (self.stats["int"] * 2); self.data["hp"] = min(self.stats["max_hp"], self.data["hp"] + heal)
            self.data["potions"] -= 1; self.combat_log.append(f"🧪 Healed +{heal} HP.")

        self.enemy["hp"] -= p_dmg
        if self.enemy["hp"] > 0:
            e_dmg = self.enemy["power"]
            if self.enemy["intent"] == "Heavy Attack": e_dmg = int(e_dmg * 1.5)
            mitigation = (self.stats["vit"] // 3) + p_block
            final_dmg = max(0, e_dmg - mitigation)
            self.data["hp"] -= final_dmg
            self.combat_log.append(f"👾 {self.enemy['name']} hits for {final_dmg} (Mitigated {mitigation}).")
            self.enemy["intent"] = random.choice(["Attack", "Heavy Attack", "Defend"])
        
        if self.enemy["hp"] <= 0:
            xp_gain = 20 + self.data["floor"]; gold_gain = 10 + (self.data["floor"] * 2)
            self.data["xp"] += xp_gain; self.data["gold"] += gold_gain; self.data["floor"] += 1
            self.mode = "EXPLORE"; self.enemy = None; req = self.data["level"] * 100
            if self.data["xp"] >= req:
                self.data["xp"] -= req; self.data["level"] += 1
                self.data["stats"]["str"] += 1; self.data["stats"]["vit"] += 1
                self.combat_log.append("✨ LEVEL UP! Stats Increased.")
            save_tower_data(self.user_id, self.data); self.render_main_menu()
            await interaction.edit_original_response(embed=self.update_embed("Victory!", f"Enemy Defeated.\n+{xp_gain} XP | +{gold_gain} Gold"), view=self)
        elif self.data["hp"] <= 0:
            self.data["hp"] = 0; lost_gold = int(self.data["gold"] / 2)
            self.data["gold"] -= lost_gold; self.data["floor"] = max(1, self.data["floor"] - 5)
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("💀 Defeated", f"You fainted.\nLost {lost_gold} Gold.\nFloor reduced."), view=None)
        else:
            save_tower_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.update_embed("Combat", "Fighting..."), view=self)

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

    @discord.slash_command(name="tower", description="Play RPG Tower")
    async def tower(self, ctx):
        view = TowerGameView(ctx.author)
        embed = view.update_embed("The Shadow Tower", "You enter the dark tower...")
        await safe_reply(ctx, embed=embed, view=view)

def setup(bot):
    bot.add_cog(TowerCog(bot))
