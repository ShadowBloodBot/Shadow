import re
import discord

SUSPICIOUS_TERMS = [
    "onlyfans", "artist", "cashapp", "crypto", "promo", "twitter", "dm me", "adult",
    "discount", "deal", "free", "follow me", "link in bio", "snapchat", "👅", "💦"
]

LINK_PATTERN = re.compile(r"https?://|discord\.gg|\.com|\.xyz|\.link|\.bio|\.site")

def get_flag_score_for_bio(bio: str) -> int:
    score = 0
    if not bio:
        return 0
    bio = bio.lower()
    if any(term in bio for term in SUSPICIOUS_TERMS):
        score += 3
    if LINK_PATTERN.search(bio):
        score += 2
    return score

def get_severity_score(member: discord.Member, bio_text: str = "") -> int:
    score = 0
    if member.bot:
        score += 1
    if "spam" in member.name.lower() or "nitro" in member.name.lower():
        score += 4
    if len(member.roles) <= 1:
        score += 2
    if not member.avatar:
        score += 1
    if (discord.utils.utcnow() - member.created_at).days <= 7:
        score += 1
    score += get_flag_score_for_bio(bio_text)
    return score

def suggest_action(member: discord.Member, bio_text: str = "") -> str:
    score = get_severity_score(member, bio_text)
    if score >= 6:
        return "Ban Likely"
    elif score >= 4:
        return "ShadowMute Recommended"
    elif score >= 2:
        return "Monitor"
    return "Low Risk"

async def ai_flag_user(member: discord.Member, client: discord.Client) -> bool:
    try:
        user = await client.fetch_user(member.id)
        profile = await user.fetch_profile()
        bio = profile.bio or ""
    except Exception as e:
        print(f"[BIO FETCH FAIL] {member}: {e}")
        bio = ""
    score = get_severity_score(member, bio)
    print(f"[AI SCORE] {member.name}: {score} | Bio: {bio[:100]}")
    return score >= 4
