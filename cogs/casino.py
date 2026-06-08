# cogs/casino.py
import os
import json
import time
import random
import asyncio
from pathlib import Path

import discord
from discord import Option, ButtonStyle, SelectOption, Interaction, ApplicationContext
from discord.ui import View, Button, Modal, TextInput, Select
from discord.ext import commands

# --- CONSTANTS ---
THEME_PRIMARY = 0x2B0B35
THEME_WIN = 0x43B581
THEME_LOSS = 0xF04747
THEME_GOLD = 0xFFD700
THEME_INFO = 0x3498DB
THEME_WARNING = 0xE67E22

CASINO_CHANNEL_ID = 1468766727134249091
# This is the Member Role ID provided for the Hybrid Security Architecture
GAMBLER_ROLE_ID = 955600320287887400
OWNER_ID = 482463400929263627
SCOIN_PULL_AMOUNT = 5
SCOIN_COOLDOWN_HOURS = 3

# Architectural Rule: Single server only. Bind commands directly to the guild cache.
# IMPORTANT: Replace this with your actual Quinfall server ID before deploying.
TARGET_GUILD_ID = 123456789012345678 

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
    except Exception as e: 
        print(f"⚠️ Persistence Error [{file_path.name}]: {e}")

def _save_scoins(): _atomic_write(SCOINS_STORE, scoins_db)

def get_balance(user_id: str) -> int: return scoins_db.get(str(user_id), {}).get("balance", 0)

def update_balance(user_id: str, amount: int):
    user_id = str(user_id)
    if user_id not in scoins_db: scoins_db[user_id] = {"balance": 0, "last_pull": 0}
    scoins_db[user_id]["balance"] += amount
    _save_scoins()

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

# --- GENERIC BET MODAL ---
class BetAmountModal(Modal):
    def __init__(self, title, balance, callback_func):
        super().__init__(title=title[:45])
        self.balance = balance
        self.callback_func = callback_func
        self.add_item(TextInput(label=f"Amount (Max: {balance})"[:45], placeholder="Enter amount or 'all'", min_length=1))
        
    async def callback(self, interaction: Interaction):
        raw = self.children[0].value.lower().strip()
        if raw == "all": amount = self.balance
        else:
            try: amount = int(raw)
            except: return await interaction.response.send_message("❌ Invalid number.", ephemeral=True)
            
        if amount <= 0: return await interaction.response.send_message("❌ Must bet > 0.", ephemeral=True)
        if amount > self.balance: return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)
        await self.callback_func(interaction, amount)


# --- [ENGINE] BLACKJACK ---
def calculate_hand(hand):
    total, aces = 0, 0
    for card in hand:
        if card in ['J', 'Q', 'K']: total += 10
        elif card == 'A': aces += 1; total += 11
        else: total += int(card)
    while total > 21 and aces: 
        total -= 10
        aces -= 1
    return total

class BlackjackView(View):
    def __init__(self, user, bet):
        super().__init__(timeout=180)
        self.user = user
        self.user_id = str(user.id)
        self.bet = bet
        self.game_over = False
        self.deck = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A'] * 4
        random.shuffle(self.deck)
        
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        
        update_balance(self.user_id, -self.bet)

        p_val = calculate_hand(self.player_hand)
        d_val = calculate_hand(self.dealer_hand)
        if p_val == 21 or d_val == 21:
            self.resolve_game()

    def generate_embed(self):
        p_val = calculate_hand(self.player_hand)
        p_cards = " ".join(f"`{c}`" for c in self.player_hand)
        
        if self.game_over:
            d_val = calculate_hand(self.dealer_hand)
            d_cards = " ".join(f"`{c}`" for c in self.dealer_hand)
        else:
            d_val = "?"
            d_cards = f"`{self.dealer_hand[0]}` `?`"

        color = THEME_PRIMARY
        status = "Game in progress... Choose your action."
        
        if self.game_over:
            if p_val > 21:
                status = f"💥 BUST! You went over 21. Lost **{self.bet}** Scoins."
                color = THEME_LOSS
            elif d_val > 21:
                payout = self.bet * 2
                update_balance(self.user_id, payout)
                status = f"🎉 Dealer Busts! You won **{payout}** Scoins."
                color = THEME_WIN
            elif p_val == 21 and len(self.player_hand) == 2 and d_val != 21:
                payout = int(self.bet * 2.5)
                update_balance(self.user_id, payout)
                status = f"🔥 BLACKJACK! You won **{payout}** Scoins."
                color = THEME_GOLD
            elif p_val > d_val:
                payout = self.bet * 2
                update_balance(self.user_id, payout)
                status = f"✅ You Win! Won **{payout}** Scoins."
                color = THEME_WIN
            elif p_val == d_val:
                update_balance(self.user_id, self.bet)
                status = f"🤝 Push. Bet of **{self.bet}** returned."
                color = 0x95A5A6
            else:
                status = f"❌ Dealer Wins. Lost **{self.bet}** Scoins."
                color = THEME_LOSS

        embed = discord.Embed(title="🃏 High-Stakes Blackjack", description=status, color=color)
        embed.add_field(name=f"Your Hand ({p_val})", value=p_cards, inline=True)
        embed.add_field(name=f"Dealer's Hand ({d_val})", value=d_cards, inline=True)
        embed.set_footer(text=f"Bet: {self.bet} Scoins")
        return embed

    def resolve_game(self):
        self.game_over = True
        for child in self.children: child.disabled = True
        if calculate_hand(self.player_hand) <= 21:
            while calculate_hand(self.dealer_hand) < 17:
                self.dealer_hand.append(self.deck.pop())

    @discord.ui.button(label="Hit", style=ButtonStyle.primary, custom_id="bj_hit")
    async def hit(self, button, interaction: Interaction):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        self.player_hand.append(self.deck.pop())
        if calculate_hand(self.player_hand) >= 21:
            self.resolve_game()
        else:
            if len(self.children) > 2: self.children[2].disabled = True
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="Stand", style=ButtonStyle.secondary, custom_id="bj_stand")
    async def stand(self, button, interaction: Interaction):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        self.resolve_game()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)

    @discord.ui.button(label="Double Down", style=ButtonStyle.danger, custom_id="bj_double")
    async def double_down(self, button, interaction: Interaction):
        if interaction.user.id != self.user.id: return await interaction.response.send_message("🚫 Not your game.", ephemeral=True)
        if get_balance(self.user_id) < self.bet:
            return await interaction.response.send_message("❌ Insufficient funds to double down.", ephemeral=True)
        
        update_balance(self.user_id, -self.bet)
        self.bet *= 2
        self.player_hand.append(self.deck.pop())
        self.resolve_game()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)


# --- [ENGINE] LIMBO (CRASH) ---
class LimboModal(Modal):
    def __init__(self, balance):
        super().__init__(title="Limbo (Crash Multiplier)"[:45])
        self.balance = balance
        self.add_item(TextInput(label=f"Bet Amount (Max: {balance})"[:45], placeholder="Enter amount or 'all'"))
        self.add_item(TextInput(label="Target Multiplier (e.g., 2.0, 10.5)"[:45], placeholder="Minimum 1.01", value="2.0"))
        
    async def callback(self, interaction: Interaction):
        raw_bet = self.children[0].value.lower().strip()
        if raw_bet == "all": bet = self.balance
        else:
            try: bet = int(raw_bet)
            except: return await interaction.response.send_message("❌ Invalid bet amount.", ephemeral=True)
            
        try: target = float(self.children[1].value.replace(',', '.'))
        except: return await interaction.response.send_message("❌ Invalid target multiplier.", ephemeral=True)

        if bet <= 0 or target < 1.01:
            return await interaction.response.send_message("❌ Bet must be > 0 and Target must be >= 1.01.", ephemeral=True)
        if bet > self.balance:
            return await interaction.response.send_message("❌ Insufficient funds.", ephemeral=True)

        user_id = str(interaction.user.id)
        update_balance(user_id, -bet)

        # Cryptographic representation of a 1% house edge crash game
        crash_point = 0.99 / (1.0 - random.random())
        
        # --- PHASE 1: LAUNCH ---
        start_embed = discord.Embed(
            title="📈 Limbo Crash", 
            description="🚀 **The rocket is launching...**\n`1.00x`", 
            color=THEME_INFO
        )
        start_embed.set_footer(text=f"Bet: {bet} | Target: {target}x")
        await interaction.response.send_message(embed=start_embed, ephemeral=True)

        # --- PHASE 2: ANIMATION ---
        # If it doesn't crash instantly, simulate a build-up frame
        if crash_point > 1.15:
            await asyncio.sleep(1.2)
            mid_point = 1.0 + ((min(crash_point, target) - 1.0) * random.uniform(0.4, 0.7))
            mid_embed = discord.Embed(
                title="📈 Limbo Crash", 
                description=f"🔥 **Climbing!**\n`{mid_point:.2f}x`", 
                color=THEME_WARNING
            )
            mid_embed.set_footer(text=f"Bet: {bet} | Target: {target}x")
            try: await interaction.edit_original_response(embed=mid_embed)
            except: pass

        await asyncio.sleep(1.5)

        # --- PHASE 3: RESOLUTION ---
        if crash_point >= target:
            payout = int(bet * target)
            update_balance(user_id, payout)
            color = THEME_WIN
            desc = f"🚀 The multiplier crashed at **{crash_point:.2f}x**!\n✅ You hit your target of **{target}x** and won **{payout}** Scoins!"
        else:
            color = THEME_LOSS
            desc = f"💥 The multiplier crashed at **{crash_point:.2f}x**.\n❌ You missed your target of **{target}x** and lost **{bet}** Scoins."

        final_embed = discord.Embed(title="📈 Limbo Crash", description=desc, color=color)
        final_embed.set_footer(text=f"Bet: {bet} | Target: {target}x")
        try: await interaction.edit_original_response(embed=final_embed)
        except: pass


# --- [ENGINE] DUEL & SHOP ---
class DuelAcceptView(View):
    def __init__(self, p1, p2, amount):
        super().__init__(timeout=60)
        self.p1 = p1
        self.p2 = p2
        self.amount = amount

    @discord.ui.button(label="ACCEPT DUEL", style=ButtonStyle.danger, emoji="⚔️")
    async def accept(self, button, interaction: Interaction):
        if interaction.user.id != self.p2.id: return
        if get_balance(str(self.p1.id)) < self.amount or get_balance(str(self.p2.id)) < self.amount:
            return await interaction.response.send_message("❌ Someone went broke during the wait.", ephemeral=True)
        
        update_balance(str(self.p1.id), -self.amount)
        update_balance(str(self.p2.id), -self.amount)
        
        winner = random.choice([self.p1, self.p2])
        loser = self.p2 if winner == self.p1 else self.p1
        win_amt = self.amount * 2
        
        update_balance(str(winner.id), win_amt)
        embed = discord.Embed(title="🩸 DUEL FINISHED", description=f"🏆 **Winner:** {winner.mention}\n💀 **Loser:** {loser.mention}\n💰 **Won:** {win_amt} Scoins", color=THEME_GOLD)
        self.clear_items()
        await interaction.response.edit_message(view=self, embed=embed)

class ShopSelect(Select):
    def __init__(self):
        options = [SelectOption(label="Ban Haste", description="10,000 Scoins: Publicly banish Haste", value="ban_haste", emoji="🔨")]
        super().__init__(placeholder="Select item to buy...", min_values=1, max_values=1, options=options)
        
    async def callback(self, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        user_id = str(interaction.user.id)
        bal = get_balance(user_id)
        val = self.values[0]
        
        if val == "ban_haste":
            cost = 10000
            if bal < cost: return await interaction.response.send_message("❌ You need 10,000 Scoins.", ephemeral=True)
            update_balance(user_id, -cost)
            await interaction.response.send_message("🔨 **Haste has been BANNED!** (Not really, but you paid 10k Scoins for the flex).", ephemeral=False)


# --- REFORMED DASHBOARD ---
class CasinoDashboard(View):
    def __init__(self):
        super().__init__(timeout=None)
        
    @discord.ui.button(label="Collect Payday", style=ButtonStyle.success, emoji="💸", row=0)
    async def collect(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        user_id = str(interaction.user.id)
        user_data = scoins_db.get(user_id, {"balance": 0, "last_pull": 0})
        last = user_data.get("last_pull", 0)
        now = time.time()
        
        if now - last < (SCOIN_COOLDOWN_HOURS * 3600):
            remaining = (SCOIN_COOLDOWN_HOURS * 3600) - (now - last)
            hours = int(remaining // 3600); mins = int((remaining % 3600) // 60)
            return await interaction.response.send_message(f"⏳ **Cooldown:** {hours}h {mins}m.", ephemeral=True)
            
        update_balance(user_id, SCOIN_PULL_AMOUNT)
        scoins_db[user_id]["last_pull"] = now
        _save_scoins()
        await interaction.response.send_message(f"💰 **Payday!** +{SCOIN_PULL_AMOUNT} Scoins.", ephemeral=True)

    @discord.ui.button(label="Wallet", style=ButtonStyle.secondary, emoji="💳", row=0)
    async def wallet_btn(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        await interaction.response.send_message(f"💳 Balance: **{bal}** Scoins.", ephemeral=True)

    @discord.ui.button(label="Top Gamblers", style=ButtonStyle.secondary, emoji="🏆", row=0)
    async def leaderboard(self, button, interaction: Interaction):
        sorted_users = sorted(scoins_db.items(), key=lambda x: x[1].get("balance", 0), reverse=True)[:10]
        desc = ""
        for i, (uid, data) in enumerate(sorted_users, 1):
            desc += f"**{i}.** <@{uid}> - 💰 {data.get('balance', 0)}\n"
        embed = discord.Embed(title="🏆 Wealth Leaderboard", description=desc or "No data.", color=THEME_GOLD)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Blackjack", style=ButtonStyle.primary, emoji="🃏", row=1)
    async def blackjack(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        async def modal_callback(inter, amount):
            view = BlackjackView(inter.user, amount)
            await inter.response.send_message(embed=view.generate_embed(), view=view, ephemeral=True)
        await interaction.response.send_modal(BetAmountModal("Blackjack Bet", bal, modal_callback))

    @discord.ui.button(label="Limbo (Crash)", style=ButtonStyle.primary, emoji="📈", row=1)
    async def limbo(self, button, interaction: Interaction):
        if interaction.channel.id != CASINO_CHANNEL_ID: return await interaction.response.send_message(f"❌ Go to <#{CASINO_CHANNEL_ID}>.", ephemeral=True)
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        bal = get_balance(str(interaction.user.id))
        await interaction.response.send_modal(LimboModal(bal))

    @discord.ui.button(label="PvP Duel", style=ButtonStyle.danger, emoji="⚔️", row=2)
    async def duel(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        await interaction.response.send_message("⚔️ To duel, use the slash command: `/duel @user [amount]`", ephemeral=True)

    @discord.ui.button(label="Shop", style=ButtonStyle.secondary, emoji="🛒", row=2)
    async def shop(self, button, interaction: Interaction):
        if not is_gambler(interaction.user): return await interaction.response.send_message("⛔ Restricted.", ephemeral=True)
        view = View(); view.add_item(ShopSelect())
        await interaction.response.send_message("🛒 **Scoin Shop**", view=view, ephemeral=True)


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

    # =========================================================================
    # SECURE COMMAND DEPLOYMENT
    # =========================================================================

    @discord.slash_command(
        name="gamble", 
        description="Open High-Roller VIP Casino Dashboard",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none()
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def gamble(self, ctx: ApplicationContext):
        if ctx.channel.id != CASINO_CHANNEL_ID: return await safe_reply(ctx, f"❌ Go to <#{CASINO_CHANNEL_ID}> to gamble.", ephemeral=True)
        # Runtime block check preserved as an absolute failsafe
        if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
        embed = discord.Embed(title="🎰 ShadowSyn VIP Casino", description="Select a game below.", color=THEME_PRIMARY)
        embed.set_footer(text=f"Balance: {get_balance(str(ctx.author.id))} Scoins")
        await safe_reply(ctx, embed=embed, view=CasinoDashboard(), ephemeral=True)

    @gamble.error
    async def gamble_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(ctx, "🚫 System override denied: Missing Gambler clearance role.", ephemeral=True)

    @discord.slash_command(
        name="duel", 
        description="Duel user",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none()
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def duel(self, ctx: ApplicationContext, opponent: discord.Member, amount: str):
        if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
        if amount == "all": bet = get_balance(str(ctx.author.id))
        else: 
            try: bet = int(amount)
            except: return await safe_reply(ctx, "❌ Invalid amount.", ephemeral=True)
            
        embed = discord.Embed(title="⚔️ DUEL", description=f"{ctx.author.mention} vs {opponent.mention}\nPot: {bet*2}", color=discord.Color.red())
        await safe_reply(ctx, content=opponent.mention, embed=embed, view=DuelAcceptView(ctx.author, opponent, bet))

    @duel.error
    async def duel_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(ctx, "🚫 System override denied: Missing Gambler clearance role.", ephemeral=True)

    @discord.slash_command(
        name="wallet", 
        description="Check balance",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none()
    )
    @commands.has_role(GAMBLER_ROLE_ID)
    async def wallet(self, ctx: ApplicationContext, user: Option(discord.User, required=False)):
        if not is_gambler(ctx.author): return await safe_reply(ctx, "⛔ Restricted.", ephemeral=True)
        t = user or ctx.author
        await safe_reply(ctx, f"💳 {t.display_name}: {get_balance(str(t.id))} Scoins")

    @wallet.error
    async def wallet_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.MissingRole):
            await safe_reply(ctx, "🚫 System override denied: Missing Gambler clearance role.", ephemeral=True)

    @discord.slash_command(
        name="give_scoins", 
        description="Owner Only",
        guild_ids=[TARGET_GUILD_ID],
        default_member_permissions=discord.Permissions.none()
    )
    @owner_only()
    async def give_scoins(self, ctx: ApplicationContext, user: discord.Member, amount: int):
        update_balance(str(user.id), amount)
        await safe_reply(ctx, f"✅ Done. New balance: {get_balance(str(user.id))}", ephemeral=True)

    @give_scoins.error
    async def give_scoins_error(self, ctx: ApplicationContext, error: discord.DiscordException):
        if isinstance(error, commands.CheckFailure):
            await safe_reply(ctx, "🚫 System override denied: Owner authorization required.", ephemeral=True)

def setup(bot):
    bot.add_cog(CasinoCog(bot))
