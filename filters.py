from datetime import datetime, timezone

def get_severity_score(member):
    score = 0
    name = member.name.lower()
    bio = (member.bio or "").lower()

    # Name or ID bait
    if any(keyword in name for keyword in ["spam", "nitro", "free", "invite"]):
        score += 4

    # Bio spam flags
    if "twitter" in bio:
        score += 3

    if any(phrase in bio for phrase in ["art designer", "commission", "dm for work", "crypto", "nft", "telegram", "promote", "fiverr"]):
        score += 3

    # Default avatar
    if member.display_avatar.is_default():
        score += 1

    # Low role count
    if len(member.roles) <= 1:
        score += 2

    # Bot flag
    if member.bot:
        score += 1

    # Account creation scoring
    account_age_days = (datetime.now(timezone.utc) - member.created_at).days
    if account_age_days < 3:
        score += 4
    elif account_age_days < 14:
        score += 2

    # Discriminator pattern (optional legacy support)
    if str(member.discriminator) in ["0001", "1234"]:
        score += 1

    return score

def suggest_action(member):
    score = get_severity_score(member)

    if score >= 7:
        return "Ban Likely"
    elif score >= 5:
        return "ShadowMute Recommended"
    elif score >= 3:
        return "Monitor"
    else:
        return "Ignore"
