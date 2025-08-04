# filters.py

from datetime import datetime, timezone
import re

# Updated patterns
SUSPICIOUS_NAME_KEYWORDS = ["twitter", "free", "nitro", "nsfw", "onlyfans", ".com", "cashapp"]
BIO_KEYWORDS = [
    "dm for work", "open commissions", "commissions open", "my portfolio", "artist",
    "click here", "hire me", "promo", "graphic designer", "fiverr", "insta", "bio", "selling", "discord.gg"
]
URL_PATTERNS = [
    r"twitter\.com", r"instagram\.com", r"discord\.gg", r"linktr\.ee", r"carrd\.co", r"fiverr\.com"
]

def score_member(member):
    score = 0
    reasons = []

    if member.bot:
        return -1, "Bot account"

    # === Default avatar ===
    if member.default_avatar == member.avatar:
        score += 2
        reasons.append("Default avatar")

    # === Suspicious name (word-boundary match) ===
    if any(re.search(rf"\\b{re.escape(kw)}\\b", member.name.lower()) for kw in SUSPICIOUS_NAME_KEYWORDS):
        score += 2
        reasons.append("Suspicious username")

    # === Account age ===
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    if age_days < 7:
        score += 3
        reasons.append(f"New account ({age_days} days old)")

    # === No roles ===
    if len(member.roles) <= 1:
        score += 1
        reasons.append("No roles")

    # === Bio scoring ===
    bio = getattr(member, "bio", "")
    if bio:
        lower_bio = bio.lower()

        if any(kw in lower_bio for kw in BIO_KEYWORDS):
            score += 3
            reasons.append("Suspicious bio keywords")

        if any(re.search(pat, lower_bio) for pat in URL_PATTERNS):
            score += 3
            reasons.append("Suspicious bio links")

    reason_str = ", ".join(reasons) if reasons else "No flags"
    return score, reason_str


def get_severity_score(score: int) -> str:
    if score >= 7:
        return "🚨"
    elif score >= 4:
        return "⚠️"
    else:
        return "✅"


def suggest_action(score: int) -> str:
    if score >= 7:
        return "Ban or timeout"
    elif score >= 4:
        return "Kick or verify"
    else:
        return "Review or ignore"
