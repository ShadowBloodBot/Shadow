# filters.py

import re
from datetime import datetime, timezone

def score_member(member) -> tuple[int, str]:
    score = 0
    reasons = []

    # 1. Profile picture check
    if not member.avatar:
        score += 1
        reasons.append("No profile picture")

    # 2. Account age check (under 7 days old)
    now = datetime.now(timezone.utc)
    account_age = (now - member.created_at).days
    if account_age <= 7:
        score += 1
        reasons.append(f"New account ({account_age}d)")

    # 3. Suspicious bio terms
    bio = getattr(member, "bio", "")
    score += get_flag_score_for_bio(bio)
    if get_flag_score_for_bio(bio):
        reasons.append("Suspicious bio")

    reason_summary = ", ".join(reasons) or "No issues"
    return score, reason_summary

def get_flag_score_for_bio(bio: str) -> int:
    if not bio:
        return 0

    bio = bio.lower()
    score = 0
    flagged_terms = ["cashapp", "onlyfans", "snapchat", "crypto", "horny", "dm me", "follow my", "free nitro", "twitter", "nsfw", "💦", "👅"]

    for term in flagged_terms:
        if term in bio:
            score += 1

    return score

def suggest_action(score: int) -> str:
    if score >= 5:
        return "Ban"
    elif score >= 3:
        return "Kick"
    elif score >= 2:
        return "Timeout"
    else:
        return "Ignore"
