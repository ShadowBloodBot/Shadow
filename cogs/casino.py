# cogs/casino.py
import os
import json
import time
import random
from pathlib import Path
import discord
from discord import Option, ButtonStyle, SelectOption, Interaction
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
THEME_WIN = 0x43B581 
THEME_LOSS = 0xF04747 
THEME_GOLD = 0xFFD700 

CASINO_CHANNEL_ID = 1468766727134249091
GAMBLER_ROLE_ID = 955600320287887400  
OWNER_ID = 482463400929263627
SCOIN_PULL_AMOUNT = 5
SCOIN_COOLDOWN_HOURS = 3

# --- PERSISTENCE ---
PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try: PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except: PERSIST_ROOT = Path(".").resolve()

SCOINS_STORE = (PERSIST_ROOT / "scoins.json")
scoins_db = {}

def _atomic_write(file_path: Path, data):
    try:
        content = json.dumps(list(data) if isinstance(data, set) else data, indent=2)
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(content, encoding='utf-8')
        temp_path.replace(file_path)
    except Exception as e: print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _save_scoins(): _atomic_write(SCOINS_STORE, scoins_db)

def get_balance(user_id: str) -> int: return scoins_db.get(str(user_id), {}).get("balance", 0)

def update_balance(user_id: str, amount: int):
    user_id = str(user_id)
    if user_id not in scoins_db: scoins_db[user_id] = {"balance": 0, "last_pull": 0}
    scoins_db[user_id]["balance"] += amount; _save_scoins()

# --- HELPERS ---
def is_gambler(user):
    if not isinstance(user, discord.Member): return False
    return any(r.id == GAMBLER_ROLE_ID for r in user.roles)

def owner_only():
    def predicate(ctx): return ctx.author.id == OWNER_ID
    return commands.check(predicate)

async def safe_reply(ctx_or_inter, *args, **kwargs):
    try:
        if hasattr(ctx_or_inter, 'respond'): return await ctx_or_inter.respond(*args, **kwargs)
        elif hasattr(ctx_or_inter, 'response'):
            if not ctx_or_inter.response.is_done(): return await ctx_or_inter.response.send_message(*args, **kwargs)
            else: return await ctx_or_inter.followup.send(*args, **kwargs)
    except: return None

# --- GAMES ---
def generate_slot_result(user, bet):
    user_id = str(user.id); update_balance(user_id, -bet)
    emojis = ["🍒", "🍋", "🍇", "💎", "7️⃣", "🔔", "🍊"]
    a, b, c = random.choice(emojis), random.choice(emojis), random.choice(emojis)
    payout = 0; is_jackpot = False
    if a == b == c: payout = bet * 13; is_jackpot = True
    elif a == b or b == c or a == c: payout = int(bet * 1.5) 
    if payout > 0:
        update_balance(user_id, payout)
        col = THEME_GOLD if payout > bet * 2 else THEME_WIN
        msg = f"🎰 **{a} | {b} | {c}**\n✅ **WIN!** +{payout}"
    else:
        col = THEME_LOSS
        msg = f"🎰 **{a} | {b} | {c}**\n❌ **Lost** {bet}"
    embed = discord.Embed(description=msg, color=col)
    if user.display_avatar: embed.set_author(name=f"{user.display_name}'s Spin", icon_url=user.display_avatar.url)
    else: embed.set_author(name=f"{user.display_name}'s Spin")
    embed.set_footer(text=f"Bet: {bet} Scoins")
    return embed, is_jackpot, payout

class RepeatSpinView(View):
    def __init__(self, user_id, bet):
        super().__init__(timeout=120); self.user_id = user_id; self.bet = bet
    @discord.ui.button(label="Spin Again", style=ButtonStyle.primary, emoji="🔄")
    async def spin_btn(self, button, interaction: Interaction):
        if interaction.user.id != self.user_id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        try:
            await interaction.response.defer(ephemeral=True) 
            bal = get_balance(str(self.user_id))
            if bal < self.bet: return await interaction.followup.send(f"❌ Insufficient funds ({bal} < {self.bet}).", ephemeral=True)
            embed, is_jackpot, win_amount = generate_slot_result(interaction.user, self.bet)
            await interaction.followup.send(embed=embed, view=RepeatSpinView(self.user_id, self.bet), ephemeral=True)
            if is_jackpot:
                target_thread = interaction.guild.get_channel(CASINO_CHANNEL_ID) or await interaction.guild.fetch_channel(CASINO_CHANNEL_ID)
                if target_thread: await target_thread.send(f"🚨 **JACKPOT!** 🎰\n**{interaction.user.display_name}** just hit a **3x Match** and won **{win_amount}** Scoins!")
        except Exception as e: await interaction.followup.send(f"⚠️ Error: {e}", ephemeral=True)

class BetAmountModal(Modal):
    def __init__(self, title, balance, callback_func):
        super().__init__(title=title)
        self.balance = balance; self.callback_func = callback_func
        self.add_item(TextInput(label=f"Amount (Max: {balance})", placeholder="Enter amount or 'all'", min_length=1))
    async def callback(self, interaction: Interaction):
        raw = self.children[0].value.lower()
        if raw == "all": amount = self.balance
        else:
            try: amount = int(raw)
            except: return await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
        if amount <= 0: return await interaction.response.send_message("❌ Must bet > 0.", ephemeral=True)
        if amount > self.balance: return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        await self.callback_func(interaction, amount)

class ChickenButton(Button):
    def __init__(self, x, y, view_ref):
        super().__init__(style=ButtonStyle.secondary, label="\u200b", row=y)
        self.x = x; self.y = y; self.view_ref = view_ref; self.idx = y * 5 + x
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.view_ref.user_id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        await self.view_ref.handle_click(self, interaction)

class ChickenGameView(View):
    def __init__(self, user, bet, bones_count):
        super().__init__(timeout=180)
        self.user_id = user.id; self.user = user; self.bet = bet; self.bones_count = bones_count
        self.grid_size = 20; self.bones_indices = set(random.sample(range(self.grid_size), bones_count))
        self.revealed = set(); self.game_over = False; self.multiplier = 1.0
        for y in range(4):
            for x in range(5): self.add_item(ChickenButton(x, y, self))
        self.cashout_btn = Button(style=ButtonStyle.success, label="Cash Out", row=4, emoji="💰", disabled=True)
        self.cashout_btn.callback = self.cash_out; self.add_item(self.cashout_btn)
    def calculate_next_multiplier(self):
        remaining_tiles = self.grid_size - len(self.revealed); safe_remaining = remaining_tiles - self.bones_count
        if safe_remaining <= 0: return self.multiplier
        return self.multiplier * (remaining_tiles / safe_remaining) * 0.97 
    async def handle_click(self, button, interaction: Interaction):
        if self.game_over: return
        idx = button.idx
        if idx in self.bones_indices:
            self.game_over = True; update_balance(str(self.user_id), -self.bet)
            button.style = ButtonStyle.danger; button.emoji = "🦴"; button.label = ""
            for child in self.children:
                if isinstance(child, ChickenButton):
                    child.disabled = True
                    if child.idx in self.bones_indices and child.idx != idx: child.style = ButtonStyle.secondary; child.emoji = "🦴"
            self.cashout_btn.disabled = True
            embed = discord.Embed(title="💥 BONE!", description=f"You hit a bone and lost **{self.bet}** Scoins.", color=THEME_LOSS)
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            self.revealed.add(idx); self.multiplier = self.calculate_next_multiplier()
            button.style = ButtonStyle.success; button.emoji = "🍗"; button.label = ""; button.disabled = True
            self.cashout_btn.disabled = False; self.cashout_btn.label = f"Cash Out ({int(self.bet * self.multiplier)})"
            current_win = int(self.bet * self.multiplier)
            embed = discord.Embed(title="🍗 CHICKEN!", description=f"Multiplier: **{self.multiplier:.2f}x**\nCurrent Win: **{current_win}**", color=THEME_GOLD)
            await interaction.response.edit_message(embed=embed, view=self)
    async def cash_out(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        self.game_over = True; win_amount = int(self.bet * self.multiplier)
        update_balance(str(self.user_id), -self.bet + win_amount)
        for child in self.children: child.disabled = True
        embed = discord.Embed(title="💰 CASHED OUT", description=f"You won **{win_amount}** Scoins!\nMultiplier: **{self.multiplier:.2f}x**", color=THEME_WIN)
        await interaction.response.edit_message(embed=embed, view=self)

class ChickenDifficultySelect(Select):
    def __init__(self, user, bet):
        self.user = user; self.bet = bet
        options = [SelectOption(label="1 Bone (Safe)", value="1"), SelectOption(label="3 Bones", value="3"), SelectOption(label="5 Bones", value="5"), SelectOption(label="10 Bones", value="10"), SelectOption(label="15 Bones", value="15")]
        super().__init__(placeholder="Select Difficulty...", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        bones = int(self.values[0]); bal = get_balance(str(self.user.id))
        if bal < self.bet: return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        view = ChickenGameView(self.user, self.bet, bones)
        embed = discord.Embed(title="🍗 Chicken Cross", description=f"Bet: {self.bet} | Bones: {bones}", color=THEME_PRIMARY)
        await interaction.response.edit_message(embed=embed, view=view)

class ChickenSetupView(View):
    def __init__(self, user, bet):
        super().__init__(timeout=60); self.add_item(ChickenDifficultySelect(user, bet))

class DiceGameView(View):
    def __init__(self, user, bet):
        super().__init__(timeout=60); self.user = user; self.user_id = user.id; self.bet = bet; self.game_over = False
    @discord.ui.button(label="Low (2-6) [x2]", style=ButtonStyle.primary, emoji="⬇️", row=0)
    async def low_btn(self, button, interaction: Interaction): await self.process_roll(interaction, "low")
    @discord.ui.button(label="Seven (7) [x5]", style=ButtonStyle.secondary, emoji="7️⃣", row=0)
    async def seven_btn(self, button, interaction: Interaction): await self.process_roll(interaction, "seven")
    @discord.ui.button(label="High (8-12) [x2]", style=ButtonStyle.primary, emoji="⬆️", row=0)
    async def high_btn(self, button, interaction: Interaction): await self.process_roll(interaction, "high")
    async def process_roll(self, interaction: Interaction, choice):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        if self.game_over: return
        bal = get_balance(str(self.user.id))
        if bal < self.bet: return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        update_balance(str(self.user.id), -self.bet); self.game_over = True
        d1 = random.randint(1, 6); d2 = random.randint(1, 6); total = d1 + d2
        dice_map = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
        visual = f"{dice_map[d1]} + {dice_map[d2]} = **{total}**"
        won = False; payout = 0
        if choice == "low" and total < 7: won = True; payout = int(self.bet * 2)
        elif choice == "high" and total > 7: won = True; payout = int(self.bet * 2)
        elif choice == "seven" and total == 7: won = True; payout = int(self.bet * 5)
        if won:
            update_balance(str(self.user_id), payout)
            embed = discord.Embed(title="🎲 Dice Roll", description=f"{visual}\n✅ **WIN!** You won **{payout}** Scoins.", color=THEME_WIN)
        else:
            embed = discord.Embed(title="🎲 Dice Roll", description=f"{visual}\n❌ **LOSS.** You lost **{self.bet}** Scoins.", color=THEME_LOSS)
        for child in self.children: child.disabled = True
        self.add_item(PlayAgainDiceButton(self.user, self.bet))
        await interaction.response.edit_message(embed=embed, view=self)

class PlayAgainDiceButton(Button):
    def __init__(self, user, bet):
        super().__init__(label="Roll Again", style=ButtonStyle.success, emoji="🔄", row=1); self.user = user; self.bet = bet
    async def callback(self, interaction: Interaction):
        if interaction.user.id != self.user.id: return
        bal = get_balance(str(self.user.id))
        if bal < self.bet: return await interaction.response.send_message("❌ Broke.", ephemeral=True)
        await interaction.response.send_message(f"🎲 **High/Low Dice**\nBet: **{self.bet}**", view=DiceGameView(self.user, self.bet), ephemeral=True)

class DuelAcceptView(View):
    def __init__(self, p1, p2, amount):
        super().__init__(timeout=60); self.p1 = p1; self.p2 = p2; self.amount = amount
    @discord.ui.button(label="ACCEPT DUEL", style=ButtonStyle.danger, emoji="⚔️")
    async def accept(self, button, interaction: Interaction):
        if interaction.user.id != self.p2.id: return
        if get_balance(str(self.p1.id)) < self.amount or get_balance(str(self.p2.id)) < self.amount:
            return await interaction.response.send_message("❌ Someone went broke during the wait.", ephemeral=True)
        update_balance(str(self.p1.id), -self.amount); update_balance(str(self.p2.id), -self.amount)
        winner = random.choice([self.p1, self.p2]); loser = self.p2 if winner == self.p1 else self.p1
        win_amt = self.amount * 2; update_balance(str(winner.id), win_amt)
        embed = discord.Embed(title="🩸 DUEL FINISHED", description=f"🏆 **Winner:** {winner.mention}\n💀 **Loser:** {loser.mention}\n💰 **Won:** {win_amt} Scoins", color=THEME_GOLD)
        self.clear_items(); await interaction.response.edit_message(view=self, embed=embed)

class ShopSelect(Select):
    def __init__(self):
        options = [SelectOption(label="Ban Haste", description="10,000 Scoins: Publicly banish Haste", value="ban_haste", emoji="🔨")]
        super().__init__(placeholder="Select item to buy...", min_values=1, max_values=1, options=options)
    async def callback(self, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        user_id = str(interaction.user.id); bal = get_balance(user_id); val = self.values[0]
        if val == "ban_haste":
            cost = 10000
            if bal < cost: return await interaction.response.send_message("❌ You need 10,000 Scoins.", ephemeral=True)
            update_balance(user_id, -cost)
            await interaction.response.send_message("🔨 **Haste has been BANNED!** (Not really, but you paid 10k Scoins for the flex).", ephemeral=False)

class CasinoDashboard(View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Collect", style=ButtonStyle.success, emoji="💰", row=0)
    async def collect(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        user_id = str(interaction.user.id); user_data = scoins_db.get(user_id, {"balance": 0, "last_pull": 0})
        last = user_data["last_pull"]; now = time.time()
        if now - last < (SCOIN_COOLDOWN_HOURS * 3600):
            remaining = (SCOIN_COOLDOWN_HOURS * 3600) - (now - last)
            hours = int(remaining // 3600); mins = int((remaining % 3600) // 60)
            return await interaction.response.send_message(f"⏳ **Cooldown:** {hours}h {mins}m.", ephemeral=True)
        update_balance(user_id, SCOIN_PULL_AMOUNT)
        scoins_db[user_id]["last_pull"] = now; _save_scoins()
        await interaction.response.send_message(f"💰 **Payday!** +{SCOIN_PULL_AMOUNT} Scoins.", ephemeral=True)
    @discord.ui.button(label="Slots", style=ButtonStyle.primary, emoji="🎰", row=0)
    async def slots(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        async def modal_callback(inter, amount):
            embed, is_jackpot, win_amount = generate_slot_result(inter.user, amount)
            await inter.response.send_message(embed=embed, view=RepeatSpinView(inter.user.id, amount), ephemeral=True)
            if is_jackpot:
                target_thread = inter.guild.get_channel(CASINO_CHANNEL_ID) or await inter.guild.fetch_channel(CASINO_CHANNEL_ID)
                if target_thread: await target_thread.send(f"🚨 **JACKPOT!** 🎰\n**{inter.user.display_name}** just hit a **3x Match** and won **{win_amount}** Scoins!")
        await interaction.response.send_modal(BetAmountModal("Slots Bet", bal, modal_callback))
    @discord.ui.button(label="Chicken", style=ButtonStyle.primary, emoji="🍗", row=0)
    async def chicken(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        async def modal_callback(inter, amount): await inter.response.send_message("🦴 **Select Difficulty (Bones)**", view=ChickenSetupView(inter.user, amount), ephemeral=True)
        await interaction.response.send_modal(BetAmountModal("Chicken Bet", bal, modal_callback))
    @discord.ui.button(label="Dice", style=ButtonStyle.primary, emoji="🎲", row=0)
    async def dice(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        async def modal_callback(inter, amount): await inter.response.send_message(f"🎲 **High/Low Dice**\nBet: **{amount}**", view=DiceGameView(inter.user, amount), ephemeral=True)
        await interaction.response.send_modal(BetAmountModal("Dice Bet", bal, modal_callback))
    @discord.ui.button(label="Duel", style=ButtonStyle.danger, emoji="⚔️", row=1)
    async def duel(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        await interaction.response.send_message("⚔️ To duel, use: `/duel @user [amount]`", ephemeral=True)
    @discord.ui.button(label="Shop", style=ButtonStyle.secondary, emoji="🛒", row=1)
    async def shop(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        view = View(); view.add_item(ShopSelect())
        await interaction.response.send_message("🛒 **Scoin Shop**", view=view, ephemeral=True)
    @discord.ui.button(label="Wallet", style=ButtonStyle.secondary, emoji="💳", row=1)
    async def wallet_btn(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        await interaction.response.send_message(f"💳 Balance: **{bal}** Scoins.", ephemeral=True)

# --- COG SETUP ---
class CasinoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._load_data()

    def _load_data(self):
        global scoins_db
        if SCOINS_STORE.exists():
            try: scoins_db = json.loads(SCOINS_STORE.read_text())
            except: scoins_db = {}
        else: scoins_db = {}

    @discord.slash_command(name="gamble", description="Open Casino")
    async def gamble(self, ctx):
        if ctx.channel.id != CASINO_CHANNEL_ID: return await safe_reply(ctx, f"❌ Go to <#{CASINO_CHANNEL_ID}> to gamble.", ephemeral=True)
        if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
        embed = discord.Embed(title="🎰 ShadowSyn Casino", description="Welcome.", color=THEME_PRIMARY)
        embed.set_footer(text=f"Balance: {get_balance(str(ctx.author.id))}")
        await safe_reply(ctx, embed=embed, view=CasinoDashboard(), ephemeral=True)

    @discord.slash_command(name="duel", description="Duel user")
    async def duel(self, ctx, opponent: discord.Member, amount: str):
        if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
        if amount == "all": bet = get_balance(str(ctx.author.id))
        else: bet = int(amount)
        embed = discord.Embed(title="⚔️ DUEL", description=f"{ctx.author.mention} vs {opponent.mention}\nPot: {bet*2}", color=discord.Color.red())
        await safe_reply(ctx, content=opponent.mention, embed=embed, view=DuelAcceptView(ctx.author, opponent, bet))

    @discord.slash_command(name="wallet", description="Check balance")
    async def wallet(self, ctx, user: Option(discord.User, required=False)):
        if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
        t = user or ctx.author; await safe_reply(ctx, f"💳 {t.display_name}: {get_balance(str(t.id))} Scoins")

    @discord.slash_command(name="give_scoins", description="Owner Only")
    @owner_only()
    async def give_scoins(self, ctx, user: discord.Member, amount: int):
        update_balance(str(user.id), amount)
        await safe_reply(ctx, f"✅ Done. New balance: {get_balance(str(user.id))}", ephemeral=True)

def setup(bot):
    bot.add_cog(CasinoCog(bot))
