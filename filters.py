# filters.py

from datetime import datetime, timezone

def score_member(member):
    score = 0
    reasons = []

    # === Default avatar ===
    if member.default_avatar == member.avatar:
        score += 2
        reasons.append("Default avatar")

    # === Suspicious keywords in username ===
    suspicious_keywords = ["twitter", "free", "nitro", "nsfw", "onlyfans", ".com"]
    if any(word in member.name.lower() for word in suspicious_keywords):
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

    # === Animated profile picture (negative signal) ===
    if member.avatar and member.avatar.is_animated():
        score -= 1
        reasons.append("Animated profile (human signal)")

    # === Bio contains 'twitter' ===
    if hasattr(member, 'bio') and member.bio:
        if 'twitter' in member.bio.lower():
            score += 3
            reasons.append("Bio contains 'twitter'")

    reason_str = ", ".join(reasons) if reasons else "No flags"
    return score, reason_str
