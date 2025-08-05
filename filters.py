import re

# Suspicious keywords to look for in bios
SUSPICIOUS_TERMS = [
    "onlyfans", "artist", "cashapp", "crypto", "promo", "twitter", "dm me", "adult",
    "discount", "deal", "free", "follow me", "link in bio", "snapchat", "👅", "💦"
]

# Pattern to catch links
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

def get_severity_score(member, bio_text=""):
    score = 0
    if member.bot:
        score += 1
    if "spam" in member.name.lower() or "nitro" in member.name.lower():
        score += 4
    if len(member.roles) <= 1:
        score += 2
    if not member.avatar:
        score += 1
    score += get_flag_score_for_bio(bio_text)
    return score

def suggest_action(member, bio_text=""):
    score = get_severity_score(member, bio_text)
    if score >= 6:
        return "Ban Likely"
    elif score >= 4:
        return "ShadowMute Recommended"
    elif score >= 2:
        return "Monitor"
    return "Low Risk"

async def ai_flag_user(member):
    try:
        profile = await member.user.fetch_profile()
        bio = profile.bio or ""
    except:
        bio = ""
    score = get_severity_score(member, bio)
    return score >= 4
