# cogs/casino/games/blackjack.py — Elite Blackjack engine

import random

import discord
from discord import ButtonStyle
from discord.ui import View

from ..announcements import maybe_announce_win
from ..constants import (
    BLACKJACK_NATURAL_MULTIPLIER,
    RANKS,
    SUITS,
    THEME_GOLD,
    THEME_LOSS,
    THEME_NEUTRAL,
    THEME_PRIMARY,
    THEME_WIN,
)
from ..economy import get_balance, record_stat, update_balance
from ..helpers import format_coins


def _build_deck() -> list[str]:
    deck = [f"{rank}{suit}" for suit in SUITS for rank in RANKS]
    random.shuffle(deck)
    return deck


def _card_value(card: str) -> int:
    rank = card[:-1]
    if rank in {"J", "Q", "K"}:
        return 10
    if rank == "A":
        return 11
    return int(rank)


def calculate_hand(hand: list[str]) -> int:
    total = sum(_card_value(card) for card in hand)
    aces = sum(1 for card in hand if card.startswith("A"))
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def _format_card(card: str) -> str:
    rank = card[:-1]
    suit = card[-1]
    return f"`{rank}{suit}`"


class BlackjackView(View):
    def __init__(self, user: discord.User, bet: int):
        super().__init__(timeout=180)
        self.user = user
        self.user_id = str(user.id)
        self.bet = bet
        self.doubled = False
        self.game_over = False
        self.outcome_recorded = False
        self.message: discord.Message | None = None
        self.deck = _build_deck()
        self.player_hand = [self._draw(), self._draw()]
        self.dealer_hand = [self._draw(), self._draw()]
        update_balance(self.user_id, -bet)
        record_stat(self.user_id, "blackjack_hands")

        if calculate_hand(self.player_hand) == 21 or calculate_hand(self.dealer_hand) == 21:
            self._resolve()

    def _draw(self) -> str:
        if len(self.deck) < 5:
            self.deck = _build_deck()
        return self.deck.pop()

    def _status_block(self) -> tuple[str, int]:
        player_total = calculate_hand(self.player_hand)
        dealer_total = calculate_hand(self.dealer_hand)

        if not self.game_over:
            return "🃏 **Your move** — Hit, Stand, or Double Down.", THEME_PRIMARY

        if player_total > 21:
            return f"💥 **BUST** — Lost {format_coins(self.bet)}.", THEME_LOSS
        if dealer_total > 21:
            return f"🎉 **Dealer busts!** Won {format_coins(self.bet * 2)}.", THEME_WIN
        if player_total == 21 and len(self.player_hand) == 2 and dealer_total != 21:
            return f"🔥 **BLACKJACK!** Won {format_coins(int(self.bet * BLACKJACK_NATURAL_MULTIPLIER))}.", THEME_GOLD
        if player_total > dealer_total:
            return f"✅ **You win!** Won {format_coins(self.bet * 2)}.", THEME_WIN
        if player_total == dealer_total:
            return f"🤝 **Push** — {format_coins(self.bet)} returned.", THEME_NEUTRAL
        return f"❌ **Dealer wins.** Lost {format_coins(self.bet)}.", THEME_LOSS

    def _resolve_outcome(self) -> tuple[int, int, str, dict]:
        """Record the outcome and return (profit, payout, headline, flags) for announcement."""
        if self.outcome_recorded:
            return 0, 0, "", {}
        self.outcome_recorded = True

        player_total = calculate_hand(self.player_hand)
        dealer_total = calculate_hand(self.dealer_hand)
        flags: dict = {}

        if player_total > 21:
            record_stat(self.user_id, "total_lost", self.bet)
            return 0, 0, "", flags

        if dealer_total > 21:
            payout = self.bet * 2
            update_balance(self.user_id, payout)
            profit = payout - self.bet
            record_stat(self.user_id, "total_won", profit)
            return profit, payout, "Dealer bust!", flags

        if player_total == 21 and len(self.player_hand) == 2 and dealer_total != 21:
            payout = int(self.bet * BLACKJACK_NATURAL_MULTIPLIER)
            update_balance(self.user_id, payout)
            profit = payout - self.bet
            record_stat(self.user_id, "total_won", profit)
            flags["blackjack_natural"] = True
            return profit, payout, "BLACKJACK!", flags

        if player_total > dealer_total:
            payout = self.bet * 2
            update_balance(self.user_id, payout)
            profit = payout - self.bet
            record_stat(self.user_id, "total_won", profit)
            return profit, payout, "Table win!", flags

        if player_total == dealer_total:
            update_balance(self.user_id, self.bet)
            return 0, self.bet, "Push", flags

        record_stat(self.user_id, "total_lost", self.bet)
        return 0, 0, "", flags

    async def on_timeout(self) -> None:
        if not self.game_over:
            self.game_over = True
            self.outcome_recorded = True
            record_stat(self.user_id, "total_lost", self.bet)
            for child in self.children:
                child.disabled = True
            if self.message:
                try:
                    await self.message.edit(
                        content="⏰ Game timed out — bet forfeited.",
                        view=self,
                    )
                except Exception:
                    pass

    async def announce_if_notable(self, bot: discord.Client) -> None:
        profit, payout, headline, flags = self._resolve_outcome()
        if profit <= 0:
            return
        await maybe_announce_win(
            bot,
            self.user,
            "Blackjack",
            profit,
            payout,
            self.bet,
            headline,
            flags=flags,
        )

    def generate_embed(self) -> discord.Embed:
        status, color = self._status_block()
        player_total = calculate_hand(self.player_hand)
        player_cards = " ".join(_format_card(c) for c in self.player_hand)

        if self.game_over:
            dealer_total = calculate_hand(self.dealer_hand)
            dealer_cards = " ".join(_format_card(c) for c in self.dealer_hand)
            dealer_label = f"Dealer ({dealer_total})"
        else:
            dealer_total = "?"
            dealer_cards = f"{_format_card(self.dealer_hand[0])} `??`"
            dealer_label = "Dealer (Hidden)"

        embed = discord.Embed(
            title="🃏 Elite Blackjack",
            description=status,
            color=color,
        )
        embed.add_field(name=f"Your Hand ({player_total})", value=player_cards, inline=False)
        embed.add_field(name=dealer_label, value=dealer_cards, inline=False)
        embed.set_footer(
            text=f"Wager: {self.bet:,} 🪙  •  Balance: {get_balance(self.user_id):,} 🪙"
        )
        return embed

    def _resolve(self) -> None:
        self.game_over = True
        for child in self.children:
            child.disabled = True
        if calculate_hand(self.player_hand) <= 21:
            while calculate_hand(self.dealer_hand) < 17:
                self.dealer_hand.append(self._draw())

    @discord.ui.button(label="Hit", style=ButtonStyle.primary, emoji="➕", row=0)
    async def hit(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("🚫 Not your hand.", ephemeral=True)
        if self.game_over:
            return await interaction.response.send_message("Round ended.", ephemeral=True)

        self.player_hand.append(self._draw())
        if self.doubled:
            self.children[2].disabled = True
        if calculate_hand(self.player_hand) >= 21:
            self._resolve()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        if self.message is None:
            self.message = interaction.message
        if self.game_over:
            await self.announce_if_notable(interaction.client)

    @discord.ui.button(label="Stand", style=ButtonStyle.secondary, emoji="🛑", row=0)
    async def stand(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("🚫 Not your hand.", ephemeral=True)
        if self.game_over:
            return await interaction.response.send_message("Round ended.", ephemeral=True)
        self._resolve()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        if self.message is None:
            self.message = interaction.message
        await self.announce_if_notable(interaction.client)

    @discord.ui.button(label="Double", style=ButtonStyle.danger, emoji="✖️", row=0)
    async def double_down(self, button, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("🚫 Not your hand.", ephemeral=True)
        if self.game_over or self.doubled or len(self.player_hand) != 2:
            return await interaction.response.send_message("Double unavailable.", ephemeral=True)
        if get_balance(self.user_id) < self.bet:
            return await interaction.response.send_message(
                "❌ Not enough Coins to double.", ephemeral=True
            )

        update_balance(self.user_id, -self.bet)
        self.bet *= 2
        self.doubled = True
        self.player_hand.append(self._draw())
        self._resolve()
        await interaction.response.edit_message(embed=self.generate_embed(), view=self)
        if self.message is None:
            self.message = interaction.message
        await self.announce_if_notable(interaction.client)
