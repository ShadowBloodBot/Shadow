import re
import discord  # ✅ Required for type hints

def score_member(member: discord.Member) -> int:
    score = 0
    bio = member.public_flags.verified_bot if hasattr(member, "public_flags") else ""

    # Heuristic rules
    if not member.avatar:
        score += 1
    if (discord.utils.utcnow() - member.created_at).days < 7:
        score += 1
    if "twitter" in (bio or "").lower() or "free" in (bio or "").lower():
        score += 2
    if re.search(r"(click here|http[s]?://|dm me)", (bio or "").lower()):
        score += 3
    if any(term in (bio or "").lower() for term in ["crypto", "nft", "xxx", "escort"]):
        score += 3

    return score

def get_severity_score(user_data):
    score = user_data["score"]
    if score >= 7:
        return "🔥 High"
    elif score >= 4:
        return "⚠️ Medium"
    else:
        return "🟢 Low"

def suggest_action(score):
    if score >= 7:
        return "Kick immediately"
    elif score >= 4:
        return "Timeout and monitor"
    else:
        return "Approve or warn"
