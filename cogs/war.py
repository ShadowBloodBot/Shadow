# cogs/war.py
import os
import json
import traceback
from pathlib import Path
import discord
from discord import Option, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands

from cogs.guild_registry import REGISTERED_GUILD_IDS, ch_id, is_owner, resolve_channel, role_id

# --- CONSTANTS ---
THEME_COMBAT = 0xE67E22
THEME_GOLD = 0xFFD700
MASTER_ADMIN_ID = 482463400929263627

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

DPS_CLASSES = [
    "Two-Handed Sword", "Spear", "Dual Axe", "Dual Dagger", 
    "War Hammer", "Bow", "Dual Crossbow", "Elementalist"
]

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
    if is_owner(user):
        return True
    if not isinstance(user, discord.Member):
        return False
    rid = role_id(user.guild.id, "member")
    if rid is None:
        return False
    return any(r.id == rid for r in user.roles)

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
            absences = info.get("absences", [])
            
            if "stats" in info:
                stats_list = [f"{k}: {v}" for k, v in info["stats"].items()]
                stats_str = f" `[{' | '.join(stats_list)}]`"
            
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
    def __init__(self, msg_id, selected_class, existing_stats=None):
        super().__init__(title=f"Stats: {selected_class}"[:45])
        self.msg_id = msg_id; self.selected_class = selected_class
        self.stat_fields = CLASS_STATS_MAP.get(selected_class, ["HP", "AP", "DP", "MDP"])
        existing_stats = existing_stats or {}
        
        for stat in self.stat_fields:
            placeholder = "e.g., 50" if "%" in stat else "e.g., 4500"
            val_str = str(existing_stats.get(stat, ""))[:15]
            self.add_item(TextInput(label=stat, placeholder=placeholder, value=val_str, required=True, max_length=15))

    async def callback(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            uid = str(interaction.user.id)
            stat_values = {}
            for i, stat in enumerate(self.stat_fields):
                val = self.children[i].value.strip()
                clean_val = val.replace("%", "").replace(",", "")
                try:
                    float(clean_val) 
                    if "%" in stat and "%" not in val: val += "%" 
                except ValueError:
                    return await interaction.followup.send(f"❌ Validation Error: `{val}` is not a valid number.", ephemeral=True)
                stat_values[stat] = val

            if self.msg_id not in war_db: return await interaction.followup.send("❌ War not found in database.", ephemeral=True)
            if "roster" not in war_db[self.msg_id]: war_db[self.msg_id]["roster"] = {}
            if "not_attending" not in war_db[self.msg_id]: war_db[self.msg_id]["not_attending"] = []
            if uid in war_db[self.msg_id]["not_attending"]: war_db[self.msg_id]["not_attending"].remove(uid)

            if "profiles" not in war_db: war_db["profiles"] = {}
            war_db["profiles"][uid] = {"class": self.selected_class, "stats": stat_values}

            absences = []
            if uid in war_db[self.msg_id]["roster"] and isinstance(war_db[self.msg_id]["roster"][uid], dict):
                absences = war_db[self.msg_id]["roster"][uid].get("absences", [])

            war_db[self.msg_id]["roster"][uid] = {"class": self.selected_class, "absences": absences, "stats": stat_values}
            _save_wars()

            msg = await interaction.channel.fetch_message(int(self.msg_id))
            await msg.edit(embed=generate_war_embed(war_db[self.msg_id]))
            await interaction.followup.send("✅ Profile and Roster updated successfully!", ephemeral=True)
        except Exception as e:
            traceback.print_exc()
            await interaction.followup.send(f"⚠️ Internal Error: {e}", ephemeral=True)

class WarClassSelect(Select):
    def __init__(self):
        options = [SelectOption(label=name, value=name, emoji=emoji) for name, emoji in QUINFALL_CLASSES]
        super().__init__(placeholder="1. Select Class to Join...", options=options, custom_id="war_class_select", min_values=1, max_values=1, row=0)
    
    async def callback(self, interaction: Interaction):
        # FAST-PATH: Determine immediately if we need a Modal to prevent interaction timeouts
        msg_id = str(interaction.message.id)
        uid = str(interaction.user.id)
        selected_class = self.values[0]
        profile = war_db.get("profiles", {}).get(uid, {})

        # If they don't have saved stats, shoot the Modal instantly. Do not defer.
        if not profile.get("class") == selected_class or not profile.get("stats"):
            return await interaction.response.send_modal(WarStatsModal(msg_id, selected_class))

        # If they DO have stats, we can safely defer and update the DB in the background
        await interaction.response.defer(ephemeral=True)
        
        if msg_id not in war_db: 
            return await interaction.followup.send("❌ War not found.", ephemeral=True)
            
        if "roster" not in war_db[msg_id]: war_db[msg_id]["roster"] = {}
        if "not_attending" not in war_db[msg_id]: war_db[msg_id]["not_attending"] = []
        if uid in war_db[msg_id]["not_attending"]: war_db[msg_id]["not_attending"].remove(uid)

        absences = []
        if uid in war_db[msg_id]["roster"] and isinstance(war_db[msg_id]["roster"][uid], dict):
            absences = war_db[msg_id]["roster"][uid].get("absences", [])

        war_db[msg_id]["roster"][uid] = {"class": selected_class, "stats": profile["stats"], "absences": absences}
        _save_wars()
        
        msg = await interaction.channel.fetch_message(int(msg_id))
        await msg.edit(embed=generate_war_embed(war_db[msg_id]))
        await interaction.followup.send("✅ Auto-joined using your saved profile stats!", ephemeral=True)

class WarAttendanceSelect(Select):
    def __init__(self):
        options = [SelectOption(label=f"Absent Fight {i}", value=str(i), emoji="❌") for i in range(1, 6)]
        super().__init__(placeholder="2. Select Fights to MISS (Leave empty if attending all)", options=options, custom_id="war_attendance_select", min_values=0, max_values=5, row=1)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        
        if uid not in war_db[msg_id].get("roster", {}): return await interaction.response.send_message("❌ Select a Class first!", ephemeral=True)
        
        await interaction.response.defer()
        if isinstance(war_db[msg_id]["roster"][uid], str): 
            war_db[msg_id]["roster"][uid] = {"class": war_db[msg_id]["roster"][uid], "absences": self.values}
        else:
            war_db[msg_id]["roster"][uid]["absences"] = self.values
            if "fights" in war_db[msg_id]["roster"][uid]: del war_db[msg_id]["roster"][uid]["fights"]
        _save_wars()
        
        msg = await interaction.channel.fetch_message(int(msg_id))
        await msg.edit(embed=generate_war_embed(war_db[msg_id]))
        await interaction.followup.send("✅ Attendance updated.", ephemeral=True)

class WarUpdateStatsButton(Button):
    def __init__(self): super().__init__(label="Update My Stats", style=ButtonStyle.success, custom_id="war_update_stats_btn", emoji="📈", row=2)
    async def callback(self, interaction: Interaction):
        # FAST-PATH: Send Modal instantly.
        msg_id = str(interaction.message.id)
        uid = str(interaction.user.id)
        profile = war_db.get("profiles", {}).get(uid, {})
        selected_class = profile.get("class")
        
        if not selected_class:
            roster_entry = war_db.get(msg_id, {}).get("roster", {}).get(uid)
            if isinstance(roster_entry, dict): selected_class = roster_entry.get("class")
            
        if not selected_class:
            return await interaction.response.send_message("❌ You must select a class from the dropdown first!", ephemeral=True)
            
        existing_stats = profile.get("stats", {})
        # INSTANT MODAL
        await interaction.response.send_modal(WarStatsModal(msg_id, selected_class, existing_stats))

class WarNotAttendingButton(Button):
    def __init__(self): super().__init__(label="Not Attending", style=ButtonStyle.danger, custom_id="war_not_attending_btn", emoji="❌", row=2)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id)
        
        await interaction.response.defer()
        if "not_attending" not in war_db[msg_id]: war_db[msg_id]["not_attending"] = []
        if uid in war_db[msg_id].get("roster", {}): del war_db[msg_id]["roster"][uid]
        if uid not in war_db[msg_id]["not_attending"]: war_db[msg_id]["not_attending"].append(uid)
        _save_wars()
        
        msg = await interaction.channel.fetch_message(int(msg_id))
        await msg.edit(embed=generate_war_embed(war_db[msg_id]))
        await interaction.followup.send("✅ Marked as Not Attending.", ephemeral=True)

class WarLeaveButton(Button):
    def __init__(self): super().__init__(label="Remove Me", style=ButtonStyle.secondary, custom_id="war_leave_btn", emoji="🗑️", row=2)
    async def callback(self, interaction: Interaction):
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        uid = str(interaction.user.id); modified = False
        
        if uid in war_db[msg_id].get("roster", {}): del war_db[msg_id]["roster"][uid]; modified = True
        if uid in war_db[msg_id].get("not_attending", []): war_db[msg_id]["not_attending"].remove(uid); modified = True
        
        if modified: 
            await interaction.response.defer()
            _save_wars()
            msg = await interaction.channel.fetch_message(int(msg_id))
            await msg.edit(embed=generate_war_embed(war_db[msg_id]))
            await interaction.followup.send("✅ Removed from the roster event.", ephemeral=True)
        else: 
            await interaction.response.send_message("⚠️ You aren't in the roster.", ephemeral=True)

class WarClearRosterButton(Button):
    def __init__(self): super().__init__(label="Admin: Clear", style=ButtonStyle.danger, custom_id="war_admin_clear_btn", emoji="🛑", row=3)
    async def callback(self, interaction: Interaction):
        if interaction.user.id != MASTER_ADMIN_ID: return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
        
        await interaction.response.defer()
        war_db[msg_id]["roster"] = {}
        war_db[msg_id]["not_attending"] = []
        _save_wars()
        
        msg = await interaction.channel.fetch_message(int(msg_id))
        await msg.edit(embed=generate_war_embed(war_db[msg_id]))
        await interaction.followup.send("🛑 Roster cleared by Admin.", ephemeral=True)

# ==================== DRAFT MODE & UI ====================

class DraftSelect(Select):
    def __init__(self, role_name, pool, selected_uids, stat_name, row):
        self.role_name = role_name
        self.stat_name = stat_name
        self.pool_dict = {uid: (val, name) for uid, val, name in pool}
        options = []
        
        if not pool:
            options.append(SelectOption(label="No players signed up", value="none"))
            super().__init__(placeholder=f"{role_name} (0 Available)", options=options, disabled=True, row=row)
        else:
            for uid, stat_val, name in pool[:25]: 
                options.append(SelectOption(
                    label=name[:25], 
                    value=uid, 
                    description=f"{stat_val:g} {stat_name}", 
                    default=(uid in selected_uids)
                ))
            max_val = min(len(options), 20)
            super().__init__(placeholder=f"Select {role_name}...", options=options, min_values=0, max_values=max_val, row=row)

    async def callback(self, interaction: Interaction):
        uids = [val for val in self.values if val != "none"]
        if self.role_name == "Tanks": self.view.selected_tanks = uids
        elif self.role_name == "Healers": self.view.selected_healers = uids
        elif self.role_name == "Necros": self.view.selected_necros = uids
        elif self.role_name == "DPS": self.view.selected_dps = uids
        
        for opt in self.options:
            opt.default = (opt.value in uids)
            
        await self.view.update_draft(interaction)

class WarDraftView(View):
    def __init__(self, war_title, all_tanks, all_healers, all_necros, all_dps, top_tanks, top_healers, top_necros, top_dps):
        super().__init__(timeout=900)
        self.war_title = war_title
        
        self.all_tanks = all_tanks
        self.all_healers = all_healers
        self.all_necros = all_necros
        self.all_dps = all_dps
        
        self.selected_tanks = top_tanks
        self.selected_healers = top_healers
        self.selected_necros = top_necros
        self.selected_dps = top_dps

        self.add_item(DraftSelect("Tanks", all_tanks, top_tanks, "MDP", 0))
        self.add_item(DraftSelect("Healers", all_healers, top_healers, "Heal %", 1))
        self.add_item(DraftSelect("Necros", all_necros, top_necros, "HP", 2))
        self.add_item(DraftSelect("DPS", all_dps, top_dps, "AP", 3))

        publish_btn = Button(label="Publish Final Roster", style=ButtonStyle.success, emoji="✅", row=4)
        publish_btn.callback = self.publish
        self.add_item(publish_btn)

    def generate_draft_embed(self):
        embed = discord.Embed(title="🛠️ Draft: 20-Man Vanguard", description=f"**{self.war_title}**\nEdit players below before publishing.", color=THEME_GOLD)
        
        def format_team(uids, pool):
            if not uids: return "None Selected"
            pool_dict = {u: (val, name) for u, val, name in pool}
            lines = []
            for uid in uids:
                if uid in pool_dict:
                    val, name = pool_dict[uid]
                    lines.append(f"<@{uid}> - **{val:g}**")
                else: lines.append(f"<@{uid}>")
            return "\n".join(lines)

        embed.add_field(name=f"🛡️ Tanks ({len(self.selected_tanks)})", value=format_team(self.selected_tanks, self.all_tanks), inline=False)
        embed.add_field(name=f"🪄 Healers ({len(self.selected_healers)})", value=format_team(self.selected_healers, self.all_healers), inline=False)
        embed.add_field(name=f"💀 Necromancers ({len(self.selected_necros)})", value=format_team(self.selected_necros, self.all_necros), inline=False)
        embed.add_field(name=f"⚔️ DPS ({len(self.selected_dps)})", value=format_team(self.selected_dps, self.all_dps), inline=False)
        
        total = len(self.selected_tanks) + len(self.selected_healers) + len(self.selected_necros) + len(self.selected_dps)
        embed.set_footer(text=f"Total Selected: {total}/20")
        return embed

    async def update_draft(self, interaction):
        await interaction.response.edit_message(embed=self.generate_draft_embed(), view=self)

    async def publish(self, interaction):
        embed = self.generate_draft_embed()
        embed.title = "🏆 FINAL: 20-Man Vanguard"
        embed.description = f"**{self.war_title}**\nThe team has been locked in by command."
        
        all_selected = self.selected_tanks + self.selected_healers + self.selected_necros + self.selected_dps
        pings = " ".join([f"<@{uid}>" for uid in all_selected])
        
        await interaction.channel.send(content=f"**VANGUARD ROSTER DEPLOYED:**\n{pings}", embed=embed)
        await interaction.response.edit_message(content="✅ Roster successfully published to the channel!", embed=None, view=None)

class WarGenerateButton(Button):
    def __init__(self): super().__init__(label="Generate Roster", style=ButtonStyle.primary, custom_id="war_generate_btn", emoji="📋", row=3)
    async def callback(self, interaction: Interaction):
        if interaction.user.id != MASTER_ADMIN_ID: return await interaction.response.send_message("⛔ Restricted. Only the Owner can use this.", ephemeral=True)
        msg_id = str(interaction.message.id)
        if msg_id not in war_db: return await interaction.response.send_message("❌ War not found.", ephemeral=True)
            
        roster = war_db[msg_id].get("roster", {})
        war_title = war_db[msg_id].get("title", "War Roster")
        
        def parse_stat(val):
            try: return float(val.replace("%", "").replace(",", "")) if isinstance(val, str) else float(val)
            except: return 0.0

        all_tanks, all_healers, all_necros, all_dps = [], [], [], []

        for uid, info in roster.items():
            if isinstance(info, str): continue
            
            c = info.get("class"); stats = info.get("stats", {})
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"User {uid}"
            
            if c == "Sword / Shield": all_tanks.append((uid, parse_stat(stats.get("MDP", 0)), name))
            elif c == "Life Staff": all_healers.append((uid, parse_stat(stats.get("Heal Multiplier (%)", 0)), name))
            elif c == "Necromancer": all_necros.append((uid, parse_stat(stats.get("HP", 0)), name))
            elif c in DPS_CLASSES: all_dps.append((uid, parse_stat(stats.get("AP", 0)), name))

        all_tanks.sort(key=lambda x: x[1], reverse=True); all_healers.sort(key=lambda x: x[1], reverse=True)
        all_necros.sort(key=lambda x: x[1], reverse=True); all_dps.sort(key=lambda x: x[1], reverse=True)

        top_tanks = [x[0] for x in all_tanks[:4]]
        top_healers = [x[0] for x in all_healers[:4]]
        top_necros = [x[0] for x in all_necros[:4]]
        top_dps = [x[0] for x in all_dps[:8]]

        draft_view = WarDraftView(war_title, all_tanks, all_healers, all_necros, all_dps, top_tanks, top_healers, top_necros, top_dps)
        await interaction.response.send_message(content="🛠️ **Draft Mode:** Review and swap members.", embed=draft_view.generate_draft_embed(), view=draft_view, ephemeral=True)

class WarRosterView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(WarClassSelect())
        self.add_item(WarAttendanceSelect())
        self.add_item(WarUpdateStatsButton())
        self.add_item(WarNotAttendingButton())
        self.add_item(WarLeaveButton())
        self.add_item(WarGenerateButton())
        self.add_item(WarClearRosterButton())

# --- COG SETUP ---
class WarCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()

    @commands.Cog.listener()
    async def on_ready(self):
        self.bot.add_view(WarRosterView())

    def _load_data(self):
        global war_db
        if WAR_STORE.exists():
            try: war_db = json.loads(WAR_STORE.read_text())
            except: war_db = {}
        else: war_db = {}
        if "profiles" not in war_db: war_db["profiles"] = {}

    @discord.slash_command(
        name="create_war",
        description="Create a Quinfall War Roster (requires War Role)",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def create_war(self, ctx, title: Option(str, description="Title of the war"), hammer_time: Option(str, description="Paste timestamp from HammerTime")):
        if not is_war_role(ctx.author):
            return await safe_reply(ctx, "⛔ Restricted. You must have the required role.", ephemeral=True)

        target_channel = await resolve_channel(self.bot, ctx.guild.id, "war")
        if not target_channel:
            return await safe_reply(ctx, "❌ War channel thread not found.", ephemeral=True)
            
        war_data = {"title": title, "time": hammer_time, "roster": {}, "not_attending": []}
        embed = generate_war_embed(war_data); view = WarRosterView()
        
        msg = await target_channel.send(content="@everyone New War Scheduled!", embed=embed, view=view)
        war_db[str(msg.id)] = war_data; _save_wars()
        
        await safe_reply(ctx, f"✅ War roster created in {target_channel.mention}", ephemeral=True)

    @discord.slash_command(
        name="refresh_war",
        description="Admin: Restores a broken/ghosted war message without losing data",
        guild_ids=REGISTERED_GUILD_IDS,
    )
    async def refresh_war(self, ctx, message_id: Option(str, description="The ID of the broken roster message")):
        if not is_war_role(ctx.author):
            return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
        if message_id not in war_db:
            return await safe_reply(ctx, "❌ That message ID is not in the active database.", ephemeral=True)

        await ctx.defer(ephemeral=True)
        war_data = war_db[message_id]

        target_channel = await resolve_channel(self.bot, ctx.guild.id, "war")
        if not target_channel:
            return await ctx.followup.send("❌ War channel thread not found.")
        
        embed = generate_war_embed(war_data); view = WarRosterView()
        new_msg = await target_channel.send(content="🔄 **Roster Refreshed** (Fixing Interaction Error)", embed=embed, view=view)
        
        war_db[str(new_msg.id)] = war_data
        del war_db[message_id]
        _save_wars()
        
        try:
            old_msg = await target_channel.fetch_message(int(message_id))
            await old_msg.delete()
        except: pass
        
        await ctx.followup.send(f"✅ Roster perfectly restored and synced to the new message!")

def setup(bot):
    bot.add_cog(WarCog(bot))
