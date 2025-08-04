import discord
import re
import json

def get_flag_score_for_bio(bio: str) -> int:
    score = 0
    if not bio:
        return score

    lowered = bio.lower()
    if "twitter" in lowered:
        score += 3
    if "art" in lowered or "designer" in lowered:
        score += 2
    if "crypto" in lowered or "invest" in lowered:
        score += 3
    if "dm" in lowered:
        score += 2

    return score

def get_flag_score_for_username(name: str) -> int:
    suspicious_keywords = ["cheap", "promo", "boost", "follower", "nude", "xxx", "porn", "onlyfans", "free"]
    return sum(2 for word in suspicious_keywords if word in name.lower())

def get_flag_score_for_roles(roles) -> int:
    score = 0
    for role in roles:
        role_name = role.name.lower()
        if "promoter" in role_name or "artist" in role_name:
            score += 2
        if "nsfw" in role_name or "onlyfans" in role_name:
            score += 4
    return score

def get_flag_score_for_account_age(member: discord.Member) -> int:
    age_days = (discord.utils.utcnow() - member.created_at).days
    if age_days < 7:
        return 3
    elif age_days < 30:
        return 2
    return 0

async def get_severity_score(member: discord.Member, bot) -> int:
    score = 0

    # 🔍 Fetch user bio via REST (only available this way)
    try:
        user = await bot.fetch_user(member.id)
        bio = getattr(user, "bio", "")
    except Exception:
        bio = ""

    score += get_flag_score_for_bio(bio)
    score += get_flag_score_for_username(member.name)
    score += get_flag_score_for_roles(member.roles)
    score += get_flag_score_for_account_age(member)

    return score

def suggest_action(member: discord.Member) -> str:
    return "Flag for Review"

def get_flagged_users():
    try:
        with open("shadow_flags.json", "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_flagged_users(flags):
    with open("shadow_flags.json", "w") as f:
        json.dump(flags, f, indent=4)
