import discord
import re

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
    if "promoter" in lowered or "artist" in lowered:
        score += 2
    if "nsfw" in lowered or "onlyfans" in lowered:
        score += 4

    return score

def get_flag_score_for_account_age(member) -> int:
    age_days = (discord.utils.utcnow() - member.created_at).days
    if age_days < 7:
        return 3
    elif age_days < 30:
        return 2
    return 0

def get_flag_score_for_avatar(member: discord.Member) -> int:
    return 2 if not member.avatar else 0

async def get_severity_score(member, bot) -> int:
    score = 0

    try:
        user = await bot.fetch_user(member.id)
        bio = getattr(user, "bio", "")
    except Exception:
        bio = ""

    score += get_flag_score_for_bio(bio)
    score += get_flag_score_for_account_age(member)
    score += get_flag_score_for_avatar(member)

    return score

def suggest_action(member) -> str:
    return "Flag for Review"

def get_flagged_users():
    import json
    try:
        with open("shadow_flags.json", "r") as f:
            return json.load(f)
    except Exception:
        return {}

def save_flagged_users(flags):
    import json
    with open("shadow_flags.json", "w") as f:
        json.dump(flags, f, indent=4)
