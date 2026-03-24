# cogs/war.py
import os
import json
from pathlib import Path
import discord
from discord import Option, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands

# --- CONSTANTS ---
THEME_COMBAT = 0xE67E22 
THEME_GOLD = 0xFFD700 
WAR_THREAD_ID = 1475981718904242309
WAR_ROLE_ID = 955600320287887400

QUINFALL_CLASSES = [
    ("Sword / Shield", "🛡️"), ("Life Staff", "🪄"), ("Two-Handed Sword", "🗡️"),
    ("Spear", "🍢"), ("Dual Axe", "🪓"), ("Dual Dagger", "⚔️"),
    ("War Hammer", "🔨"), ("Bow", "🏹"), ("Dual Crossbow", "🎯"),
    ("Elementalist", "🔥"), ("Necromancer", "💀")
]

CLASS_STATS_MAP = {
    "Sword / Shield": ["HP", "DP", "MDP"],
    "Life Staff": ["AP", "Max Mana", "Heal Multiplier (%)"],
    "Two-Handed Sword": ["HP", "AP", "DP", "MDP"],
    "Spear": ["HP", "AP", "DP", "MDP"],
    "Dual Axe": ["HP", "AP", "DP", "MDP"],
    "Dual Dagger": ["HP", "AP", "DP", "MDP"],
    "War Hammer": ["HP", "AP", "DP", "MDP"],
    "Bow": ["HP", "AP", "DP", "MDP"],
    "Dual Crossbow": ["HP", "AP", "DP", "MDP"],
    "Elementalist": ["HP", "AP", "DP", "MDP"],
    "Necromancer": ["HP", "AP", "DP", "MDP"]
}

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

WAR_STORE = (PERSIST_ROOT / "wars.json")
war_db = {}

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e:
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _save_wars(): _atomic_write(WAR_STORE, war_db)

def is_war_role(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == WAR_ROLE_ID for r in user.roles)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

# --- LOGIC ---
def generate_war_embed(data):
    embed = discord.Embed(title=f"⚔️ {data['title']}", description=f"**Time:** {data['time']}\nSelect your class and if you'll miss any fights below!", color=THEME_COMBAT)
    class_counts = {c[0]: [] for c in QUINFALL_CLASSES}
    
    for uid, info in data.get("roster", {}).items():
        stats_str = ""
        if isinstance(info, str):
            cls = info; absences = []
        else:
            cls = info.get("class")
            if "absences" in info: absences = info["absences"]
            elif "fights" in info: absences = [f for f in ["1", "2", "3", "4", "5"] if f not in info["fights"]]
            else: absences = []
            
            if "stats" in info:
                stats_list = [f"{k}: {v}" for k, v in info["stats"].items()]
                stats_str = f" `[{' | '.join(stats_list)}]`"
            else:
                ap = info.get("ap"); dp = info.get("dp"); mdp = info.get("mdp")
                if ap and dp and mdp: stats_str = f" `[AP: {ap} | DP: {dp} | MDP: {mdp}]`"
            
        fight_str = f" *(Absent Round {', '.join(sorted(absences))})*" if absences else ""
        if cls in class_counts: class_counts[cls].append(f"<@{uid}>{stats_str}{fight_str}")
            
    total_confirmed = 0
    for class_name, emoji in QUINFALL_CLASSES:
        users = class_counts.get(class_name, [])
        if users:
            embed.add_field(name=f"{emoji} {class_name} ({len(users)})", value="\n".join(users), inline=False)
            total_confirmed += len(users)

    not_attending = data.get("not_attending", [])
    if not_attending:
        embed.add_field(name=f"❌ Not Attending ({len(not_attending)})", value="\n".join([f"<@{uid}>" for uid in not_attending]), inline=False)
            
    embed.set_footer(text=f"Total Confirmed: {total_confirmed} | Not Attending: {len(not_attending)}")
    return embed

class WarStatsModal(Modal):
    def __init__(self, msg_id, selected_class):
        super().__init__(title=f"Stats: {selected_class}"[:45])
        self.msg_id = msg_id; self.selected_class = selected_class
        self.stat_fields = CLASS_STATS_MAP.get(selected_class, ["HP", "AP", "DP", "MDP"])
        for stat in self.stat_fields:
            placeholder = "e.g., 50" if "%" in stat else "e.g., 4500"
            self.add_item(TextInput(label=stat, placeholder=placeholder, required=True, max_length=7))

    async def callback(self, interaction: Interaction):
        uid = str(interaction.user.id)
        stat_values = {}
        for i, stat in enumerate(self.stat_fields):
            val = self.children[i].value.strip()
            clean_val = val.replace("%", "").replace(",", "")
            try:
                float(clean_val) 
                if "%" in stat and "%" not in val: val += "%" 
            except ValueError:
                return await interaction.response.send_message(f"❌ Validation Error: `{val}` is not a valid number for {stat}. Please enter numbers only.", ephemeral=True)
            stat_values[stat] = val

        if self.msg_id not in war_db: return await interaction.response.send_message("❌ War not found in database.", ephemeral=True)
        if "roster" not in war_db[self.msg_id]: war_db[self.msg_id]["roster"] = {}
        if "not_attending" not in war_db[self.msg_id]: war_db[self.msg_id]["not_attending"] = []
        if uid in war_db[self.msg_id]["not_attending"]: war_db[self.msg_id]["not_attending"].remove(uid)

        absences = []
        if uid in war_db[self.msg_id]["roster"] and isinstance(war_db[self.msg_id]["roster"][uid], dict):
            absences = war_db[self.msg_id]["roster"][uid].get("absences", [])

        war_db[self.msg_id]["roster"][uid] = {"class": self.selected_class, "absences": absences, "stats": stat_values}
        _save_wars()

        try:
            msg = await interaction.channel.fetch_message(int(self.msg_id))
            await msg.edit(embed=generate_war_embed(war_db[self.msg_id]))
            await interaction.response.send_message("✅ Class and Stats updated successfully!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Saved, but failed to update embed: {e}", ephemeral=True)

class WarClassSelect(Select):
    def __init__(self):
        options = [SelectOption(label=name, value=name, emoji=emoji) for name, emoji in QUINFALL_CLASSES]
        super().__init__(placeholder="1. Select Class to Join...", options=options, custom_id="war_class_select", min_values=1, max_values=1, row=0)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found in database.", ephemeral=True)
        await interaction.response.send_modal(WarStatsModal(msg_id, self.values[0]))

class WarAttendanceSelect(Select):
    def __init__(self):
        options = [SelectOption(label=f"Absent Fight {i}", value=str(i), emoji="❌") for i in range(1, 6)]
        super().__init__(placeholder="2. Select Fights to MISS (Leave empty if attending all)", options=options, custom_id="war_attendance_select", min_values=0, max_values=5, row=1)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        if uid not in war_db[msg_id].get("roster", {}): return await interaction.response.send_message("❌ Select a Class first!", ephemeral=True)
        if isinstance(war_db[msg_id]["roster"][uid], str): 
            war_db[msg_id]["roster"][uid] = {"class": war_db[msg_id]["roster"][uid], "absences": self.values}
        else:
            war_db[msg_id]["roster"][uid]["absences"] = self.values
            if "fights" in war_db[msg_id]["roster"][uid]: del war_db[msg_id]["roster"][uid]["fights"]
        _save_wars()
        await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))

class WarNotAttendingButton(Button):
    def __init__(self): super().__init__(label="Not Attending", style=ButtonStyle.danger, custom_id="war_not_attending_btn", emoji="❌", row=2)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        if "not_attending" not in war_db[msg_id]: war_db[msg_id]["not_attending"] = []
        if uid in war_db[msg_id].get("roster", {}): del war_db[msg_id]["roster"][uid]
        if uid not in war_db[msg_id]["not_attending"]: war_db[msg_id]["not_attending"].append(uid)
        _save_wars(); await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))

class WarLeaveButton(Button):
    def __init__(self): super().__init__(label="Clear My Status", style=ButtonStyle.secondary, custom_id="war_leave_btn", emoji="🗑️", row=2)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id); modified = False
        if uid in war_db[msg_id].get("roster", {}): del war_db[msg_id]["roster"][uid]; modified = True
        if uid in war_db[msg_id].get("not_attending", []): war_db[msg_id]["not_attending"].remove(uid); modified = True
        if modified: _save_wars(); await interaction.response.edit_message(embed=generate_war_embed(war_db[msg_id]))
        else: await interaction.response.send_message("⚠️ You haven't selected a status yet.", ephemeral=True)

class WarGenerateButton(Button):
    def __init__(self): super().__init__(label="Generate 20-Man Roster", style=ButtonStyle.primary, custom_id="war_generate_btn", emoji="📋", row=3)
    async def callback(self, interaction: Interaction):
        if not is_war_role(interaction.user): return await interaction.response.send_message("⛔ Restricted to War Role.", ephemeral=True)
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
            
        roster = war_db[msg_id].get("roster", {})
        def parse_stat(val):
            try: return float(val.replace("%", "").replace(",", "")) if isinstance(val, str) else float(val)
            except: return 0.0

        tanks, healers, necros, dps = [], [], [], []

        for uid, info in roster.items():
            if isinstance(info, str): continue
            c = info.get("class"); stats = info.get("stats", {})
            if c == "Sword / Shield": tanks.append((uid, parse_stat(stats.get("MDP", 0))))
            elif c == "Life Staff": healers.append((uid, parse_stat(stats.get("Heal Multiplier (%)", 0))))
            elif c == "Necromancer": necros.append((uid, parse_stat(stats.get("HP", 0))))
            elif c in ["Elementalist", "Dual Crossbow"]: dps.append((uid, parse_stat(stats.get("AP", 0))))

        tanks.sort(key=lambda x: x[1], reverse=True); healers.sort(key=lambda x: x[1], reverse=True)
        necros.sort(key=lambda x: x[1], reverse=True); dps.sort(key=lambda x: x[1], reverse=True)

        top_tanks = tanks[:4]; top_healers = healers[:4]; top_necros = necros[:4]; top_dps = dps[:8]

        def format_team(selected_list, stat_name):
            if not selected_list: return "None"
            return "\n".join([f"<@{uid}> - **{val:g}** {stat_name}" for uid, val in selected_list])
        
        embed = discord.Embed(title="🏆 20-Man Vanguard Roster", description="Selected based on highest stat priority.", color=THEME_GOLD)
        embed.add_field(name=f"🛡️ Tanks (Top {len(top_tanks)}/4)", value=format_team(top_tanks, "MDP"), inline=False)
        embed.add_field(name=f"🪄 Healers (Top {len(top_healers)}/4)", value=format_team(top_healers, "Heal Multiplier (%)"), inline=False)
        embed.add_field(name=f"💀 Necromancers (Top {len(top_necros)}/4)", value=format_team(top_necros, "HP"), inline=False)
        embed.add_field(name=f"🏹 Ranged DPS (Top {len(top_dps)}/8)", value=format_team(top_dps, "AP"), inline=False)
        total = len(top_tanks) + len(top_healers) + len(top_necros) + len(top_dps)
        embed.set_footer(text=f"Total Selected: {total}/20")
        await interaction.response.send_message(embed=embed)

class WarRosterView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WarClassSelect())
        self.add_item(WarAttendanceSelect())
        self.add_item(WarNotAttendingButton())
        self.add_item(WarLeaveButton())
        self.add_item(WarGenerateButton())

# --- COG SETUP ---
class WarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        global war_db
        if WAR_STORE.exists():
            try: war_db = json.loads(WAR_STORE.read_text())
            except: war_db = {}
        else: war_db = {}

    @discord.slash_command(name="create_war", description="Create a Quinfall War Roster (requires War Role)")
    async def create_war(self, ctx, title: Option(str, description="Title of the war"), hammer_time: Option(str, description="Paste timestamp from HammerTime")):
        if not is_war_role(ctx.author):
            return await safe_reply(ctx, "⛔ Restricted. You must have the required role.", ephemeral=True)
            
        target_channel = self.bot.get_channel(WAR_THREAD_ID) or await self.bot.fetch_channel(WAR_THREAD_ID)
        if not target_channel: return await safe_reply(ctx, "❌ War channel thread not found.", ephemeral=True)
            
        war_data = {"title": title, "time": hammer_time, "roster": {}, "not_attending": []}
        embed = generate_war_embed(war_data); view = WarRosterView()
        
        msg = await target_channel.send(content="@everyone New War Scheduled!", embed=embed, view=view)
        war_db[str(msg.id)] = war_data; _save_wars()
        
        await safe_reply(ctx, f"✅ War roster created in {target_channel.mention}", ephemeral=True)

def setup(bot):
    bot.add_cog(WarCog(bot))
