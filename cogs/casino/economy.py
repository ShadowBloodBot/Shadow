# cogs/casino/economy.py — Atomic economy persistence & redemptions

import json
import os
import time
import uuid
from pathlib import Path

from .constants import (
    DAILY_CLAIM_AMOUNT,
    DAILY_CLAIM_SECONDS,
    ECONOMY_VERSION,
    REDEEM_COOLDOWN_SECONDS,
    REDEEM_MAX_PER_MONTH,
    STARTING_BALANCE,
)

PERSIST_ROOT = Path(os.getenv("PERSIST_PATH", "/data")).resolve()
try:
    PERSIST_ROOT.mkdir(parents=True, exist_ok=True)
except OSError:
    PERSIST_ROOT = Path(".").resolve()

SCOINS_STORE = PERSIST_ROOT / "scoins.json"
META_STORE = PERSIST_ROOT / "economy_meta.json"
REDEMPTIONS_STORE = PERSIST_ROOT / "redemptions.json"
BUYINS_STORE = PERSIST_ROOT / "buyins.json"
CASINO_PANELS_STORE = PERSIST_ROOT / "casino_panels.json"

scoins_db: dict = {}
redemptions_db: dict = {"requests": []}
buyins_db: dict = {"requests": []}
panels_db: dict = {"panels": {}}


def _atomic_write(file_path: Path, data) -> None:
    try:
        payload = json.dumps(
            list(data) if isinstance(data, set) else data,
            indent=2,
        )
        temp_path = file_path.with_suffix(".tmp")
        temp_path.write_text(payload, encoding="utf-8")
        temp_path.replace(file_path)
    except Exception as exc:
        print(f"⚠️ Persistence Error [{file_path.name}]: {exc}")


def _save_scoins() -> None:
    _atomic_write(SCOINS_STORE, scoins_db)


def _save_redemptions() -> None:
    _atomic_write(REDEMPTIONS_STORE, redemptions_db)


def _save_buyins() -> None:
    _atomic_write(BUYINS_STORE, buyins_db)


def _ensure_user(user_id: str) -> dict:
    user_id = str(user_id)
    if user_id not in scoins_db:
        scoins_db[user_id] = {
            "balance": STARTING_BALANCE,
            "last_claim": 0,
            "stats": {},
            "last_redeem": 0,
        }
    row = scoins_db[user_id]
    if "last_claim" not in row and "last_pull" in row:
        row["last_claim"] = row["last_pull"]
    row.setdefault("last_claim", 0)
    row.setdefault("stats", {})
    row.setdefault("last_redeem", 0)
    return row


def migrate_economy() -> None:
    """One-time Season 1 fresh wipe when ECONOMY_VERSION bumps."""
    global scoins_db
    meta: dict = {}
    if META_STORE.exists():
        try:
            meta = json.loads(META_STORE.read_text(encoding="utf-8"))
        except Exception:
            meta = {}

    if meta.get("version", 0) >= ECONOMY_VERSION:
        return

    scoins_db = {}
    _save_scoins()
    _atomic_write(
        META_STORE,
        {
            "version": ECONOMY_VERSION,
            "reset_at": time.time(),
            "starting_balance": STARTING_BALANCE,
            "note": "Season 1 — fresh economy. All members start at 100 Coins on first play.",
        },
    )
    print(
        f"🎰 Economy migrated to v{ECONOMY_VERSION}: fresh wipe. "
        f"New accounts start with {STARTING_BALANCE} Coins."
    )


def load_scoins() -> None:
    global scoins_db, redemptions_db, buyins_db
    migrate_economy()
    _load_panels()
    if SCOINS_STORE.exists():
        try:
            scoins_db = json.loads(SCOINS_STORE.read_text(encoding="utf-8"))
        except Exception:
            scoins_db = {}
    else:
        scoins_db = {}
    if REDEMPTIONS_STORE.exists():
        try:
            redemptions_db = json.loads(REDEMPTIONS_STORE.read_text(encoding="utf-8"))
        except Exception:
            redemptions_db = {"requests": []}
    else:
        redemptions_db = {"requests": []}
    redemptions_db.setdefault("requests", [])
    if BUYINS_STORE.exists():
        try:
            buyins_db = json.loads(BUYINS_STORE.read_text(encoding="utf-8"))
        except Exception:
            buyins_db = {"requests": []}
    else:
        buyins_db = {"requests": []}
    buyins_db.setdefault("requests", [])


def get_balance(user_id: str) -> int:
    return _ensure_user(user_id).get("balance", 0)


def update_balance(user_id: str, amount: int) -> int:
    row = _ensure_user(user_id)
    row["balance"] = max(0, row.get("balance", 0) + amount)
    _save_scoins()
    return row["balance"]


def record_stat(user_id: str, key: str, amount: int = 1) -> None:
    row = _ensure_user(user_id)
    stats = row.setdefault("stats", {})
    stats[key] = stats.get(key, 0) + amount
    if key == "total_won" and amount > stats.get("best_win", 0):
        stats["best_win"] = amount
    _save_scoins()


def _load_panels() -> None:
    global panels_db
    if CASINO_PANELS_STORE.exists():
        try:
            loaded = json.loads(CASINO_PANELS_STORE.read_text(encoding="utf-8"))
            panels_db = loaded if isinstance(loaded, dict) else {"panels": {}}
        except Exception:
            panels_db = {"panels": {}}
    else:
        panels_db = {"panels": {}}
    panels_db.setdefault("panels", {})


def _save_panels() -> None:
    _atomic_write(CASINO_PANELS_STORE, panels_db)


def get_panel_id(guild_id: int | str) -> int | None:
    raw = panels_db.get("panels", {}).get(str(guild_id))
    try:
        return int(raw) if raw else None
    except (TypeError, ValueError):
        return None


def set_panel_id(guild_id: int | str, message_id: int) -> None:
    panels_db.setdefault("panels", {})[str(guild_id)] = message_id
    _save_panels()


def clear_panel_id(guild_id: int | str) -> None:
    panels_db.get("panels", {}).pop(str(guild_id), None)
    _save_panels()


def player_stats(user_id: str) -> dict:
    row = _ensure_user(user_id)
    stats = row.get("stats", {})
    total_won = int(stats.get("total_won", 0))
    total_lost = int(stats.get("total_lost", 0))
    blackjack = int(stats.get("blackjack_hands", 0))
    roulette = int(stats.get("roulette_spins", 0))
    vault = int(stats.get("vault_heists", 0))
    return {
        "balance": int(row.get("balance", 0)),
        "total_won": total_won,
        "total_lost": total_lost,
        "net": total_won - total_lost,
        "blackjack_hands": blackjack,
        "roulette_spins": roulette,
        "vault_heists": vault,
        "games_played": blackjack + roulette + vault,
        "best_win": int(stats.get("best_win", 0)),
    }


def _metric_score(data: dict, metric: str) -> int:
    stats = data.get("stats", {})
    if metric == "balance":
        return int(data.get("balance", 0))
    if metric == "total_won":
        return int(stats.get("total_won", 0))
    if metric == "net_profit":
        return int(stats.get("total_won", 0)) - int(stats.get("total_lost", 0))
    if metric == "activity":
        return (
            int(stats.get("blackjack_hands", 0))
            + int(stats.get("roulette_spins", 0))
            + int(stats.get("vault_heists", 0))
        )
    return 0


def top_by_metric(metric: str, limit: int = 10) -> list[tuple[str, int]]:
    ranked = sorted(
        scoins_db.items(),
        key=lambda item: _metric_score(item[1], metric),
        reverse=True,
    )
    out: list[tuple[str, int]] = []
    for uid, data in ranked:
        val = _metric_score(data, metric)
        if val <= 0 and metric != "balance":
            continue
        out.append((uid, val))
        if len(out) >= limit:
            break
    return out


def claim_status(user_id: str) -> tuple[bool, int]:
    row = _ensure_user(user_id)
    last = float(row.get("last_claim", 0))
    elapsed = time.time() - last
    if elapsed >= DAILY_CLAIM_SECONDS:
        return True, 0
    return False, int(DAILY_CLAIM_SECONDS - elapsed)


def process_daily_claim(user_id: str) -> tuple[bool, str, int]:
    can_claim, remaining = claim_status(user_id)
    if not can_claim:
        hours = remaining // 3600
        mins = (remaining % 3600) // 60
        return False, f"⏳ Daily claim resets in **{hours}h {mins}m**.", get_balance(user_id)

    row = _ensure_user(user_id)
    row["balance"] = row.get("balance", 0) + DAILY_CLAIM_AMOUNT
    row["last_claim"] = time.time()
    _save_scoins()
    return (
        True,
        f"💰 **Daily stipend claimed!** +{DAILY_CLAIM_AMOUNT:,} Coins.",
        row["balance"],
    )


def top_balances(limit: int = 10) -> list[tuple[str, int]]:
    ranked = sorted(
        scoins_db.items(),
        key=lambda item: item[1].get("balance", 0),
        reverse=True,
    )
    return [(uid, data.get("balance", 0)) for uid, data in ranked[:limit]]


def get_pending_redemption(user_id: str) -> dict | None:
    user_id = str(user_id)
    for req in redemptions_db.get("requests", []):
        if req.get("user_id") == user_id and req.get("status") == "pending":
            return req
    return None


def count_monthly_redemptions(user_id: str) -> int:
    user_id = str(user_id)
    now = time.time()
    month_ago = now - (30 * 86_400)
    return sum(
        1
        for req in redemptions_db.get("requests", [])
        if req.get("user_id") == user_id
        and req.get("status") in {"pending", "approved"}
        and req.get("created_at", 0) >= month_ago
    )


def redeem_cooldown_remaining(user_id: str) -> int:
    row = _ensure_user(user_id)
    last = float(row.get("last_redeem", 0))
    if not last:
        return 0
    elapsed = time.time() - last
    if elapsed >= REDEEM_COOLDOWN_SECONDS:
        return 0
    return int(REDEEM_COOLDOWN_SECONDS - elapsed)


def create_redemption(user_id: str, tier: dict, steam_id: str) -> dict:
    user_id = str(user_id)
    cost = tier["coins"]
    balance = get_balance(user_id)
    if balance < cost:
        raise ValueError("Insufficient balance.")
    if get_pending_redemption(user_id):
        raise ValueError("You already have a pending redemption.")
    if count_monthly_redemptions(user_id) >= REDEEM_MAX_PER_MONTH:
        raise ValueError("Monthly redemption limit reached.")

    update_balance(user_id, -cost)
    request = {
        "id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "tier_id": tier["id"],
        "coins": cost,
        "usd": tier["usd"],
        "steam_id": steam_id,
        "status": "pending",
        "created_at": time.time(),
    }
    redemptions_db.setdefault("requests", []).append(request)
    _save_redemptions()
    return request


def resolve_redemption(request_id: str, approved: bool, admin_id: int) -> dict | None:
    for req in redemptions_db.get("requests", []):
        if req.get("id") != request_id or req.get("status") != "pending":
            continue
        req["status"] = "approved" if approved else "denied"
        req["resolved_at"] = time.time()
        req["resolved_by"] = str(admin_id)
        if approved:
            row = _ensure_user(req["user_id"])
            row["last_redeem"] = time.time()
            _save_scoins()
        else:
            update_balance(req["user_id"], req["coins"])
        _save_redemptions()
        return req
    return None


def pending_redemptions() -> list[dict]:
    return [r for r in redemptions_db.get("requests", []) if r.get("status") == "pending"]


def get_pending_buyin(user_id: str) -> dict | None:
    user_id = str(user_id)
    for req in buyins_db.get("requests", []):
        if req.get("user_id") == user_id and req.get("status") == "pending":
            return req
    return None


def count_monthly_buyins(user_id: str) -> int:
    user_id = str(user_id)
    month_ago = time.time() - (30 * 86_400)
    return sum(
        1
        for req in buyins_db.get("requests", [])
        if req.get("user_id") == user_id
        and req.get("status") == "approved"
        and req.get("created_at", 0) >= month_ago
    )


def create_buyin(user_id: str, tier: dict, payment_ref: str) -> dict:
    user_id = str(user_id)
    from .constants import BUYIN_MAX_PER_MONTH

    if get_pending_buyin(user_id):
        raise ValueError("You already have a pending buy-in. Wait for admin review.")
    if count_monthly_buyins(user_id) >= BUYIN_MAX_PER_MONTH:
        raise ValueError("Monthly buy-in limit reached.")

    request = {
        "id": uuid.uuid4().hex[:12],
        "user_id": user_id,
        "tier_id": tier["id"],
        "usd": tier["usd"],
        "coins": tier["coins"],
        "payment_ref": payment_ref,
        "status": "pending",
        "created_at": time.time(),
    }
    buyins_db.setdefault("requests", []).append(request)
    _save_buyins()
    return request


def resolve_buyin(request_id: str, approved: bool, admin_id: int) -> dict | None:
    for req in buyins_db.get("requests", []):
        if req.get("id") != request_id or req.get("status") != "pending":
            continue
        req["status"] = "approved" if approved else "denied"
        req["resolved_at"] = time.time()
        req["resolved_by"] = str(admin_id)
        if approved:
            update_balance(req["user_id"], req["coins"])
        _save_buyins()
        return req
    return None


def pending_buyins() -> list[dict]:
    return [r for r in buyins_db.get("requests", []) if r.get("status") == "pending"]
