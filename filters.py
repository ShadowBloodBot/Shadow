# filters.py

from datetime import datetime, timezone
import re

# Keywords and patterns
SUSPICIOUS_NAME_KEYWORDS = ["twitter", "free", "nitro", "nsfw", "onlyfans", ".com", "join my", "cashapp"]
BIO_KEYWORDS = [
    "dm for work", "open commissions", "commissions open", "my portfolio",
    "artist", "click here", "hire me", "promo", "graphic designer", "fiverr", "insta", "instagram", "bio"
]
URL_PATTERNS = [r"twitter\.com", r"instagram\.com", r"discord\.gg", r"linktr\.ee", r"carrd\.co"]


def score_member(member):
    score = 0
    reasons = []

    # === Skip if bot ===
    if member.bot:
        return -1, "Bot account"

    # === Default avatar ===
    if member.default_avatar == member.avatar:
        score += 2
        reasons.append("Default avatar")

    # === Suspicious username ===
    if any(kw in member.name.lower() for kw in SUSPICIOUS_NAME_KEYWORDS):
        score += 2
        reasons.append("Suspicious username")

    # === Account age < 7 days ===
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    if age_days < 7:
        score += 3
        reasons.append(f"New account ({age_days} days old)")

    # === No roles besides @everyone ===
    if len(member.roles) <= 1:
        score += 1
        reasons.append("No roles")

    # === Bio scoring ===
    bio = getattr(member, "bio", "")
    if bio:
        lower_bio = bio.lower()

        # Keyword matches
        if any(kw in lower_bio for kw in BIO_KEYWORDS):
            score += 3
            reasons.append("Suspicious bio keywords")

        # Link pattern matches
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
