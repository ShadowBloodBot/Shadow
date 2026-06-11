# cogs/casino/constants.py — ShadowSyn VIP Casino configuration

import os

THEME_PRIMARY = 0x2B0B35
THEME_WIN = 0x43B581
THEME_LOSS = 0xF04747
THEME_GOLD = 0xFFD700
THEME_INFO = 0x3498DB
THEME_WARNING = 0xE67E22
THEME_NEUTRAL = 0x95A5A6

CASINO_CHANNEL_ID = 1468766727134249091
GAMBLER_ROLE_ID = 955600320287887400
OWNER_ID = 482463400929263627
TARGET_GUILD_ID = 908659586536468540

# ── Economy peg: 1,000 Coins = $1 USD · 10 Coins = 1¢ ──
ECONOMY_VERSION = 2
COINS_PER_USD = 1_000
COINS_PER_CENT = 10
STARTING_BALANCE = 100
DAILY_CLAIM_AMOUNT = 100
DAILY_CLAIM_SECONDS = 86_400

MIN_BET = COINS_PER_CENT
MAX_BET = 2_500
QUICK_BETS = [10, 50, 100, 250, 500]

# ── Steam shop ──
SHOP_MIN_COINS = 20_000
SHOP_TIERS = [
    {"id": "steam_20", "coins": 20_000, "usd": 20, "emoji": "🥉", "label": "$20 Steam Wallet"},
    {"id": "steam_30", "coins": 30_000, "usd": 30, "emoji": "🥈", "label": "$30 Steam Wallet"},
    {"id": "steam_50", "coins": 50_000, "usd": 50, "emoji": "🥇", "label": "$50 Steam Wallet"},
    {"id": "steam_100", "coins": 100_000, "usd": 100, "emoji": "💎", "label": "$100 Steam Wallet"},
]
REDEEM_COOLDOWN_SECONDS = 7 * 86_400
REDEEM_MAX_PER_MONTH = 2
MEMBER_TENURE_DAYS = 14
_steam_redeem_env = os.getenv("STEAM_REDEEM_CHANNEL_ID", "").strip()
STEAM_REDEEM_CHANNEL_ID = (
    int(_steam_redeem_env) if _steam_redeem_env else CASINO_CHANNEL_ID
)
BUYIN_PAYMENT_URL = os.getenv(
    "BUYIN_PAYMENT_URL", "https://paypal.me/ShadowSyn001"
).strip().rstrip("/")
BUYIN_PAYMENT_LABEL = os.getenv("BUYIN_PAYMENT_LABEL", "PayPal").strip()
BUYIN_MAX_PENDING = 1
BUYIN_MAX_PER_MONTH = 8

# Peg-aligned: $1 = 1,000 Coins (same rate as Steam shop)
BUYIN_TIERS = [
    {"id": "buyin_1", "usd": 1, "coins": 1_000, "emoji": "💵", "label": "$1 Buy-In"},
    {"id": "buyin_2", "usd": 2, "coins": 2_000, "emoji": "💵", "label": "$2 Buy-In"},
    {"id": "buyin_3", "usd": 3, "coins": 3_000, "emoji": "💵", "label": "$3 Buy-In"},
    {"id": "buyin_4", "usd": 4, "coins": 4_000, "emoji": "💵", "label": "$4 Buy-In"},
    {"id": "buyin_5", "usd": 5, "coins": 5_000, "emoji": "💵", "label": "$5 Buy-In"},
]

# ── House edge tuning ──
VAULT_HOUSE_MULTIPLIER = 0.965
BLACKJACK_NATURAL_MULTIPLIER = 2.4

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]

ROULETTE_RED = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
