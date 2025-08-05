# filters.py

from datetime import datetime, timezone
import re

SUSPICIOUS_NAME_KEYWORDS = [
    "twitter", "free", "nitro", "nsfw", "onlyfans", ".com", "cashapp"
]

BIO_KEYWORDS = [
    "dm for work", "open commissions", "commissions open", "my portfolio",
    "hire me", "promo", "graphic designer", "freelance", "looking for work"
]

LINK_PATTERNS = [
    r"http[s]?://", r"\.com\b", r"discord\.gg", r"x\.com", r"linktr\.ee",
    r"instagram\.com", r"fiverr\.com", r"onlyfans\.com", r"carrd\.co"
]

def score_member(member, user):
    score = 0
    reasons = []

    if member.bot:
        return -1, "Bot account"

    # === Default avatar ===
    if member.default_avatar == member.avatar:
        score += 2
        reasons.append("Default avatar")

    # === Suspicious username ===
    if any(re.search(rf"\b{re.escape(kw)}\b", member.name.lower()) for kw in SUSPICIOUS_NAME_KEYWORDS):
        score += 2
        reasons.append("Suspicious username")

    # === Account age ===
    age_days = (datetime.now(timezone.utc) - member.created_at).days
    if age_days < 7:
        score += 3
        reasons.append(f"New account ({age_days} days old)")

    # === Bio scanning ===
    bio = getattr(user, "bio", None)
    if bio:
        lower_bio = bio.lower()

        if any(phrase in lower_bio for phrase in BIO_KEYWORDS):
            score += 3
            reasons.append("Bio keyword")

        if any(re.search(pat, lower_bio) for pat in LINK_PATTERNS):
            score += 2
            reasons.append("Link in bio")

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
