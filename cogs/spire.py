# cogs/spire.py
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

# --- CYBERPUNK CONSTANTS ---
THEME_CYAN = 0x00F0FF 
THEME_PINK = 0xFF003C 
THEME_HACK = 0x00FF00 
THEME_CORP = 0xFCEE0A 

RARITY_COLORS = {
    "Standard": 0x95A5A6, 
    "Upgraded": 0x2ECC71, 
    "High-End": 0x3498DB, 
    "Mil-Spec": 0x9B59B6, 
    "Prototype": 0xE67E22, 
    "Black-Market": 0xFF003C
}

ITEM_SLOTS = ["Neural Link", "Cyberarm", "Exosuit", "Optics"] 

ENEMIES = {
    1: ["Maintenance Bot", "Alley Junkie", "Low-Level Scrapper", "Rogue Drone"],
    5: ["Corp-Sec Guard", "Combat Drone", "Cyber-Hound", "Street Samurai"],
    15: ["Elite Operative", "Riot Mech", "Net-Runner", "Heavy Gunner"],
    30: ["Black-ICE Avatar", "Cyborg Assassin", "Corporate Enforcer", "Stealth Drone"],
    50: ["Megacorp CEO", "Orbital Defense System", "Digital God", "Apex AI"]
} 

SECTORS = {
    "The Slums": {"range": (1, 20), "color": 0x2ECC71, "emoji": "🏙️", "effect": "Smog: 5% Acid Dmg every 5 turns."},
    "Industrial Grid": {"range": (21, 40), "color": 0x95A5A6, "emoji": "🏭", "effect": "Interference: 20% Miss Chance."},
    "Executive Suites": {"range": (41, 60), "color": THEME_CORP, "emoji": "🏢", "effect": "Security: Skills cost 5 HP."},
    "The Mainframe": {"range": (61, 999), "color": THEME_PINK, "emoji": "🌐", "effect": "System Overload: Enemies have 20% execute chance."}
}

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve() 
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

SPIRE_STORE = (PERSIST_ROOT / "spire_db.json") 
spire_db = {}

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e: print(f"⚠️ Persistence Error: {e}") 

def _save_spire(): _atomic_write(SPIRE_STORE, spire_db) 

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except Exception as e: return None 

# --- CORE LOGIC ---
def get_runner_data(user_id):
    uid = str(user_id)
    if uid not in spire_db:
        spire_db[uid] = {
            "sector": 1, "hp": 100, "max_hp": 100, "credits": 0, "stims": 3, 
            "level": 1, "xp": 0, "stats": {"gpu": 5, "psu": 5, "ram": 5, "cpu": 5},
            "cyberware": {"Neural Link": None, "Cyberarm": None, "Exosuit": None, "Optics": None},
            "inventory": [], "overdrive": 0, "data_shards": 0, "kills": 0, "deaths": 0, "bounty": 0
        }
    
    d = spire_db[uid]
    for key in ["data_shards", "kills", "deaths", "bounty", "credits", "sector", "xp", "level", "hp"]:
        if key not in d: d[key] = 0
        else: d[key] = int(d[key])
    return d

def save_runner_data(user_id, data):
    spire_db[str(user_id)] = data
    _save_spire()

def get_total_stats(data):
    total = data["stats"].copy()
    for slot in ITEM_SLOTS:
        item = data["cyberware"].get(slot)
        if item:
            for stat, val in item.get("stats", {}).items():
                total[stat] = total.get(stat, 0) + val
    total["atk"] = total["gpu"] * 2
    total["max_hp"] = 100 + (total["psu"] * 10)
    total["crit_chance"] = min(50, total["ram"] * 0.5)
    total["hack_dmg_mult"] = 1 + (total["cpu"] * 0.05)
    return total 

def generate_cyberware(sector, black_market=False):
    if black_market:
        rarity = "Black-Market"
        budget = sector + 60
    else:
        roll = random.randint(1, 100)
        if roll > 98: rarity = "Prototype"
        elif roll > 85: rarity = "Mil-Spec"
        elif roll > 60: rarity = "High-End"
        elif roll > 30: rarity = "Upgraded"
        else: rarity = "Standard"
        budget = sector + ({"Standard": 2, "Upgraded": 5, "High-End": 10, "Mil-Spec": 20, "Prototype": 40}[rarity])
        
    slot = random.choice(ITEM_SLOTS)
    stats = {}
    possible_stats = ["gpu", "psu", "ram", "cpu"]
    num_stats = {"Standard": 1, "Upgraded": 2, "High-End": 3, "Mil-Spec": 4, "Prototype": 4, "Black-Market": 4}[rarity]
    
    for _ in range(num_stats):
        s = random.choice(possible_stats)
        val = max(1, int(budget / num_stats))
        stats[s] = stats.get(s, 0) + val
        
    if black_market:
        stats["psu"] = -abs(max(5, int(budget / 4))) 
        name = f"Corrupted {slot} (Malware)"
    else:
        prefix = {"gpu": "Assault", "psu": "Aegis", "ram": "Reflex", "cpu": "Logic"}
        dominant = max(stats, key=stats.get)
        name = f"{rarity} {slot} [{prefix[dominant]}]"

    return {"id": str(uuid.uuid4())[:8], "name": name, "rarity": rarity, "slot": slot, "stats": stats, "value": budget * 5}

def get_sector(sector_num):
    for name, data in SECTORS.items():
        if data["range"][0] <= sector_num <= data["range"][1]: return name, data
    return "The Mainframe", SECTORS["The Mainframe"]

def draw_bar(curr, max_val, color="🟩", empty="⬛", length=10):
    if max_val <= 0: return empty * length
    pct = max(0.0, min(1.0, float(curr) / float(max_val)))
    fill = int(pct * length)
    if fill == 0 and curr > 0: fill = 1 
    return color * fill + empty * (length - fill) 

# --- CONCRETE UI COMPONENTS ---
class ActionBtn(Button):
    def __init__(self, action_id, label, style, emoji, row):
        super().__init__(label=label, style=style, emoji=emoji, row=row)
        self.action_id = action_id
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.view.user_id: return await interaction.response.send_message("🚫 Unauthorized User.", ephemeral=True)
        await self.view.handle_action(interaction, self.action_id)

class CyberwareSelect(Select):
    def __init__(self, options, row): super().__init__(placeholder="Install Cyberware...", options=options, row=row)
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.view.user_id: return await interaction.response.send_message("🚫 Unauthorized User.", ephemeral=True)
        await self.view.equip_callback(interaction, self.values[0])

# --- SYSTEM VIEWS ---
class HackTerminalView(View):
    def __init__(self, user):
        super().__init__(timeout=120); self.user = user; self.data = get_runner_data(user.id)
        btn_hack = Button(label="Inject Malware (-10 PSU, +3 All)", style=ButtonStyle.danger, emoji="💉")
        btn_hack.callback = self.inject
        self.add_item(btn_hack)
        
        btn_extract = Button(label="Data Heist (20% Virus, 80% Prototype)", style=ButtonStyle.primary, emoji="💾")
        btn_extract.callback = self.extract
        self.add_item(btn_extract)
        
        btn_logoff = Button(label="Disconnect", style=ButtonStyle.secondary, emoji="🔌")
        btn_logoff.callback = self.logoff
        self.add_item(btn_logoff)
        
    async def inject(self, interaction):
        if interaction.user.id != self.user.id: return
        self.data["stats"]["psu"] = max(1, self.data["stats"]["psu"] - 10)
        for s in ["gpu", "ram", "cpu"]: self.data["stats"][s] += 3
        self.data["hp"] = min(self.data["hp"], get_total_stats(self.data)["max_hp"])
        save_runner_data(self.user.id, self.data)
        view = SpireGameView(self.user)
        await interaction.response.edit_message(embed=view.build_embed("System Overridden", "Hardware damaged, but processing limits bypassed."), view=view)

    async def extract(self, interaction):
        if interaction.user.id != self.user.id: return
        roll = random.randint(1, 100)
        if roll <= 20:
            item = generate_cyberware(self.data["sector"], black_market=True)
            msg = "FIREWALL BREACHED. Malware downloaded to neural link."
        else:
            item = generate_cyberware(self.data["sector"] + 20)
            item["rarity"] = "Prototype"
            msg = "Encryption cracked. Top-tier schematic acquired."
        self.data["inventory"].append(item)
        save_runner_data(self.user.id, self.data)
        view = SpireGameView(self.user)
        await interaction.response.edit_message(embed=view.build_embed("Terminal Output", f"{msg}\nInstalled: **{item['name']}**."), view=view)

    async def logoff(self, interaction):
        if interaction.user.id != self.user.id: return
        view = SpireGameView(self.user)
        await interaction.response.edit_message(embed=view.build_embed("Network", "Connection severed. You step away from the terminal."), view=view)

class SpireGameView(View):
    def __init__(self, user):
        super().__init__(timeout=300)
        self.user = user; self.user_id = user.id 
        self.data = get_runner_data(user.id)
        self.stats = get_total_stats(self.data)
        self.mode = "NAV" ; self.enemy = None; self.log = []
        self.data["hp"] = int(min(float(self.data["hp"]), float(self.stats["max_hp"])))
        self.render_ui() 

    def build_embed(self, title, desc):
        if self.mode == "VAULT": return self.embed_vault()
        elif self.mode == "VENDOR": return self.embed_vendor()
        
        s_name, s_data = get_sector(self.data['sector'])
        hp_bar = draw_bar(self.data["hp"], self.stats["max_hp"], "🟩", "⬛", 12)
        od_bar = draw_bar(self.data.get("overdrive", 0), 100, "🟪", "⬛", 12)
        
        color = s_data["color"] if self.mode != "COMBAT" else THEME_PINK
        embed = discord.Embed(title=f"{s_data['emoji']} {title} | Sector {self.data['sector']}", description=desc, color=color)
        
        if self.mode == "COMBAT" and self.enemy:
            e_bar = draw_bar(self.enemy['hp'], self.enemy['max_hp'], "🟥", "⬛", 12)
            embed.add_field(name=f"🆚 {self.enemy['name']}", value=f"{e_bar} `[{self.enemy['hp']} HP]`\n⚠️ **Protocol:** {self.enemy.get('intent', 'Idle')}", inline=False)
            if self.log: 
                log_text = "\n".join(self.log[-5:])
                embed.add_field(name="Terminal_Log.exe", value=f"```ansi\n{log_text}\n```", inline=False)
                
        disp = f"⚔️ GPU:{self.stats['atk']} | 🛡️ PSU:{self.stats['psu']//2} | 💳 ₡{self.data['credits']}"
        embed.add_field(name=f"👤 Operator: {self.user.display_name} `[Lv.{self.data['level']}]`", value=f"`[INTEGRITY]` {hp_bar} {self.data['hp']}\n`[OVERDRIVE]` {od_bar}\n{disp}", inline=False)
        embed.set_footer(text=f"Network: {s_name} | {s_data['effect']}")
        return embed 

    def embed_vault(self):
        stats = get_total_stats(self.data)
        embed = discord.Embed(title=f"💾 {self.user.display_name}'s Cyber-Vault", color=THEME_CYAN)
        embed.add_field(name="System Diagnostics", value=f"❤️ **Integrity:** {self.data['hp']}/{stats['max_hp']}\n⚔️ **Damage:** {stats['atk']} (GPU: {stats['gpu']})\n🛡️ **Armor:** {stats['psu'] // 2} (PSU: {stats['psu']})\n⚡ **Speed:** {stats['crit_chance']}% (RAM: {stats['ram']})\n💀 **Shards:** {self.data.get('data_shards', 0)}", inline=True)
        
        cw_text = ""
        for slot in ITEM_SLOTS:
            item = self.data["cyberware"].get(slot)
            if item: cw_text += f"**{slot}:** {item['name']} `[{''.join([f'+{v}{k[:1].upper()}' for k,v in item['stats'].items()])}]`\n"
            else: cw_text += f"**{slot}:** None\n"
        embed.add_field(name="Installed Cyberware", value=cw_text, inline=False)
        
        inv = "\n".join([f"• {i['name']}" for i in self.data['inventory'][:5]]) if self.data["inventory"] else "Vault is empty."
        embed.add_field(name=f"Storage Backup ({len(self.data['inventory'])} items)", value=inv, inline=False)
        return embed

    def embed_vendor(self):
        embed = discord.Embed(title="🛒 Black Market Vendor", description="\"Got the creds, runner?\"", color=THEME_CORP)
        embed.add_field(name="Your Account", value=f"💳 {self.data['credits']} Credits\n💾 {self.data.get('data_shards', 0)} Shards")
        embed.add_field(name="Inventory", value=f"💉 {self.data['stims']} Nano-Stims")
        embed.add_field(name="Bounty Rating", value=f"🎯 ₡{self.data.get('bounty', 0)}")
        return embed

    def render_ui(self):
        self.clear_items()
        if self.mode == "COMBAT":
            self.add_item(ActionBtn("atk", "Fire Weapon", ButtonStyle.danger, "🔫", 0))
            self.add_item(ActionBtn("def", "Firewall", ButtonStyle.secondary, "🛡️", 0))
            if self.data["stims"] > 0: self.add_item(ActionBtn("stim", f"Stim ({self.data['stims']})", ButtonStyle.success, "💉", 0))
            if self.data["overdrive"] >= 100: self.add_item(ActionBtn("ult", "SYSTEM OVERRIDE", ButtonStyle.primary, "⚡", 1))
        elif self.mode == "NAV":
            self.add_item(ActionBtn("ascend", "Infiltrate Next Sector", ButtonStyle.success, "🧗", 0))
            self.add_item(ActionBtn("rest", "Reboot (100₡)", ButtonStyle.primary, "💤", 0))
            self.add_item(ActionBtn("vault", "Cyber-Vault", ButtonStyle.secondary, "💾", 1))
        elif self.mode == "VAULT":
            if self.data["inventory"]:
                opts = [SelectOption(label=f"{i['name']} ({i['slot']})", value=i["id"]) for i in self.data["inventory"][:25]]
                self.add_item(CyberwareSelect(opts, 0))
            self.add_item(ActionBtn("back", "Close Vault", ButtonStyle.secondary, "↩️", 1))
        elif self.mode == "VENDOR":
            self.add_item(ActionBtn("buy", "Buy Stim (50₡)", ButtonStyle.success, "💉", 0))
            self.add_item(ActionBtn("sell", "Liquidate Hardware", ButtonStyle.danger, "💳", 0))
            self.add_item(ActionBtn("leave", "Exit Market", ButtonStyle.secondary, "🚪", 1))

    async def equip_callback(self, interaction, val):
        await interaction.response.defer() 
        item = next((i for i in self.data["inventory"] if i["id"] == val), None)
        if item:
            slot = item["slot"]; cur = self.data["cyberware"].get(slot)
            if cur: self.data["inventory"].append(cur)
            self.data["cyberware"][slot] = item; self.data["inventory"].remove(item)
            save_runner_data(self.user_id, self.data); self.stats = get_total_stats(self.data) 
            self.render_ui() 
            await interaction.edit_original_response(embed=self.build_embed("System Updated", "Hardware integrated successfully."), view=self)

    async def handle_action(self, interaction, action):
        try:
            if not interaction.response.is_done(): await interaction.response.defer()
            if action in ["atk", "def", "stim", "ult"]: await self.run_combat(interaction, action)
            elif action == "vault":
                self.mode = "VAULT"; self.render_ui()
                await interaction.edit_original_response(embed=self.build_embed("Vault", ""), view=self)
            elif action == "back":
                self.mode = "NAV"; self.render_ui()
                await interaction.edit_original_response(embed=self.build_embed("Navigation", "Awaiting input..."), view=self)
            elif action in ["buy", "sell", "leave"]: await self.run_vendor(interaction, action)
            elif action in ["ascend", "rest"]: await self.run_nav(interaction, action)
        except Exception: traceback.print_exc()

    async def run_vendor(self, interaction, action):
        if action == "buy":
            if self.data["credits"] >= 50:
                self.data["credits"] -= 50; self.data["stims"] += 1; save_runner_data(self.user_id, self.data)
                await interaction.edit_original_response(embed=self.build_embed("Market", "Transaction complete. Stim acquired."), view=self)
            else: await interaction.followup.send("❌ Insufficient funds.", ephemeral=True)
        elif action == "sell":
            total = sum([i["value"] for i in self.data["inventory"]]); count = len(self.data["inventory"])
            self.data["inventory"] = []; self.data["credits"] += total; save_runner_data(self.user_id, self.data)
            await interaction.edit_original_response(embed=self.build_embed("Market", f"Liquidated {count} components for ₡{total}."), view=self)
        elif action == "leave":
            self.mode = "NAV"; self.data["sector"] += 1; self.render_ui()
            await interaction.edit_original_response(embed=self.build_embed("Infiltration", "Moving deeper into the Spire."), view=self)

    async def run_nav(self, interaction, action):
        if action == "rest":
            if self.data["credits"] >= 100:
                self.data["credits"] -= 100; self.data["hp"] = self.stats["max_hp"]; save_runner_data(self.user_id, self.data)
                await interaction.edit_original_response(embed=self.build_embed("💤 System Reboot", "Integrity fully restored."), view=self)
            else: await interaction.followup.send("❌ Need ₡100.", ephemeral=True)
        elif action == "ascend":
            if self.data["sector"] % 5 == 0 and self.data["sector"] > 1:
                self.mode = "VENDOR"; self.render_ui()
                await interaction.edit_original_response(embed=self.build_embed("Safe Room", "A hidden black-market node discovered."), view=self)
                return
            roll = random.randint(1, 100)
            if roll <= 10:
                await interaction.edit_original_response(embed=discord.Embed(title="💻 Black-ICE Terminal", description="An exposed corporate terminal. Risk a hack?", color=THEME_HACK), view=HackTerminalView(self.user))
            elif roll <= 40: 
                item = generate_cyberware(self.data["sector"])
                desc = f"Encrypted cache cracked.\n\n**{item['name']}**\n" + "\n".join([f"• **{k.upper()}:** +{v}" for k,v in item['stats'].items()]) + f"\n\n*Street Value: ₡{item['value']}*"
                view = View(); btn = Button(label="Loot", style=ButtonStyle.success, emoji="🎒")
                async def take(i): 
                    if i.user.id != self.user.id: return
                    self.data["inventory"].append(item); save_runner_data(self.user.id, self.data)
                    self.render_ui(); await i.response.edit_message(embed=self.build_embed("Looted", f"Acquired {item['name']}."), view=self)
                btn.callback = take; view.add_item(btn)
                await interaction.edit_original_response(embed=discord.Embed(title="📦 Cache Found", description=desc, color=RARITY_COLORS.get(item['rarity'], 0xFFFFFF)), view=view)
            else: 
                self.mode = "COMBAT"; floor = self.data["sector"]; name = get_monster(floor)
                self.enemy = {"name": name, "hp": (floor * 25) + 80, "max_hp": (floor * 25) + 80, "power": (floor * 3) + 5, "intent": random.choice(["Target Locked", "Overclocking"])}
                self.log = [f"> SYSTEM ALERT: {name} engaged!"]; self.render_ui()
                await interaction.edit_original_response(embed=self.build_embed("⚔️ HOSTILE DETECTED", "Lethal force authorized."), view=self)

    async def run_combat(self, interaction, action):
        if not self.enemy: return
        p_dmg, p_block = 0, 0
        if action == "atk":
            dmg = self.stats["atk"] + random.randint(-2, 2)
            if random.randint(1, 100) <= self.stats["crit_chance"]: dmg = int(dmg * 1.5); self.log.append(f"> CRITICAL HIT: {dmg} DMG dealt.")
            else: self.log.append(f"> Weapon fired: {dmg} DMG.")
            p_dmg = dmg; self.data["overdrive"] = min(100, self.data["overdrive"] + 10)
        elif action == "def":
            p_block = self.stats["psu"]; self.log.append(f"> Firewall active. Absorbing {p_block} DMG.")
            self.data["overdrive"] = min(100, self.data["overdrive"] + 5)
        elif action == "ult":
            p_dmg = self.stats["atk"] * 3; self.log.append(f"> OVERRIDE EXECUTED: Massive {p_dmg} DMG!"); self.data["overdrive"] = 0
        elif action == "stim":
            heal = 50 + (self.stats["cpu"] * 2); self.data["hp"] = min(self.stats["max_hp"], self.data["hp"] + heal)
            self.data["stims"] -= 1; self.log.append(f"> Stim injected: +{heal} Integrity.")

        self.enemy["hp"] -= p_dmg
        if self.enemy["hp"] > 0:
            e_dmg = self.enemy["power"] if self.enemy["intent"] == "Target Locked" else int(self.enemy["power"] * 1.5)
            mitigation = (self.stats["psu"] // 3) + p_block
            final_dmg = max(0, e_dmg - mitigation)
            self.data["hp"] -= final_dmg
            self.log.append(f"> WARNING: Incoming damage -> {final_dmg}.")
            self.enemy["intent"] = random.choice(["Target Locked", "Overclocking", "Recharging"])
        
        if self.enemy["hp"] <= 0:
            xp, creds = 20 + self.data["sector"], 10 + (self.data["sector"] * 2)
            self.data["xp"] += xp; self.data["credits"] += creds; self.data["sector"] += 1
            if self.data["sector"] > 10: self.data["data_shards"] += 1
            self.mode = "NAV"; self.enemy = None
            if self.data["xp"] >= self.data["level"] * 100:
                self.data["xp"] -= self.data["level"] * 100; self.data["level"] += 1
                self.data["stats"]["gpu"] += 1; self.data["stats"]["psu"] += 1
                self.log.append("> LEVEL UP! Firmware upgraded.")
            save_runner_data(self.user_id, self.data); self.render_ui()
            await interaction.edit_original_response(embed=self.build_embed("Target Eliminated", f"Threat neutralized.\n+{xp} XP | +₡{creds}"), view=self)
        elif self.data["hp"] <= 0:
            self.data["hp"] = 0; lost = int(self.data["credits"] / 2); self.data["credits"] -= lost
            self.data["sector"] = max(1, self.data["sector"] - 5); self.data["deaths"] += 1
            save_runner_data(self.user_id, self.data); await interaction.edit_original_response(embed=self.build_embed("💀 FLATLINED", f"System failure. Lost ₡{lost}."), view=None)
        else:
            save_runner_data(self.user_id, self.data); await interaction.edit_original_response(embed=self.build_embed("Combat", "Engaged."), view=self)

# --- COG SETUP ---
class SpireCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        global spire_db
        if SPIRE_STORE.exists():
            try: spire_db = json.loads(SPIRE_STORE.read_text())
            except: spire_db = {}
        else: spire_db = {}

    @discord.slash_command(name="spire", description="Infiltrate the Mega-Spire.")
    async def spire(self, ctx):
        try:
            view = SpireGameView(ctx.author)
            await safe_reply(ctx, embed=view.build_embed("The Spire", "Jacking into the network. No turning back."), view=view)
        except Exception as e: await safe_reply(ctx, f"⚠️ Error: {e}", ephemeral=True)

    @discord.slash_command(name="spire_heist", description="Invade a rival's network and steal credits.")
    async def spire_heist(self, ctx, target: Option(discord.Member, "Target to hack.")):
        try:
            if ctx.author.id == target.id: return await safe_reply(ctx, "❌ Cannot target own network.", ephemeral=True)
            u1, u2 = get_runner_data(ctx.author.id), get_runner_data(target.id)
            if str(target.id) not in spire_db: return await safe_reply(ctx, "❌ Target IP not found.", ephemeral=True)
            s1, s2 = get_total_stats(u1), get_total_stats(u2)
            
            cp1 = (s1["atk"] + s1["psu"]) * random.uniform(0.85, 1.15)
            cp2 = (s2["atk"] + s2["psu"]) * random.uniform(0.85, 1.15)

            embed = discord.Embed(title="🌐 Net-Heist", color=THEME_PINK)
            if cp1 > cp2:
                stolen = int(u2["credits"] * 0.15); u2["credits"] -= stolen; u1["credits"] += stolen + u2["bounty"]
                bounty = f"\n🎯 **Bounty Claimed:** ₡{u2['bounty']}" if u2["bounty"] > 0 else ""
                u2["bounty"] = 0; u1["kills"] += 1; u2["deaths"] += 1; u1["data_shards"] += 5
                embed.description = f"**{ctx.author.display_name}** breached **{target.display_name}**'s firewall.\n\n💰 **Stolen:** ₡{stolen}{bounty}\n💾 **Gained:** 5 Shards"; embed.color = THEME_HACK
            else:
                stolen = int(u1["credits"] * 0.15); u1["credits"] -= stolen; u2["credits"] += stolen; u2["kills"] += 1; u1["deaths"] += 1; u2["data_shards"] += 5
                embed.description = f"**{ctx.author.display_name}** was disconnected by **{target.display_name}**'s ICE.\n\n💰 **Lost:** ₡{stolen}\n💀 Connection severed."; embed.color = THEME_PINK

            save_runner_data(ctx.author.id, u1); save_runner_data(target.id, u2)
            await safe_reply(ctx, embed=embed)
        except Exception as e: await safe_reply(ctx, f"⚠️ Error: {e}", ephemeral=True)

    @discord.slash_command(name="spire_bounty", description="Place a hit on a rival.")
    async def spire_bounty(self, ctx, target: Option(discord.Member), amount: Option(int)):
        if amount <= 0: return await safe_reply(ctx, "❌ Must be > 0.", ephemeral=True)
        u1 = get_runner_data(ctx.author.id)
        if u1["credits"] < amount: return await safe_reply(ctx, "❌ Insufficient funds.", ephemeral=True)
        u2 = get_runner_data(target.id); u1["credits"] -= amount; u2["bounty"] += amount
        save_runner_data(ctx.author.id, u1); save_runner_data(target.id, u2)
        await safe_reply(ctx, embed=discord.Embed(title="🎯 Contract Issued", description=f"Bounty of ₡{amount} placed on {target.display_name}.", color=THEME_CORP))

    @discord.slash_command(name="spire_board", description="View the Shadow-Net Leaderboard.")
    async def spire_board(self, ctx):
        players = [(uid, data) for uid, data in spire_db.items() if isinstance(data, dict) and "sector" in data]
        if not players: return await safe_reply(ctx, "No data.", ephemeral=True)
        
        embed = discord.Embed(title="🌐 The Shadow-Net", color=THEME_CYAN)
        embed.add_field(name="🧗 Top Infiltrators", value="\n".join([f"<@{u}>: Sector {d.get('sector', 0)}" for u, d in sorted(players, key=lambda x: x[1].get("sector", 0), reverse=True)[:5]]) or "None", inline=False)
        embed.add_field(name="💀 Apex Hackers", value="\n".join([f"<@{u}>: {d.get('kills', 0)} Hacks" for u, d in sorted(players, key=lambda x: x[1].get("kills", 0), reverse=True)[:5] if d.get("kills", 0) > 0]) or "None", inline=False)
        await safe_reply(ctx, embed=embed)

def setup(bot):
    bot.add_cog(SpireCog(bot))
