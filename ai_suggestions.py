def suggest_action(member):
    if "spam" in member.name.lower() or "nitro" in member.name.lower():
        return "Ban Likely"
    if len(member.roles) <= 1:
        return "ShadowMute Recommended"
    if member.bot:
        return "Audit Bot"
    return "Monitor"

def get_severity_score(member):
    score = 0
    if member.bot:
        score += 1
    if "spam" in member.name.lower() or "nitro" in member.name.lower():
        score += 4
    if len(member.roles) <= 1:
        score += 2
    if not member.avatar:
        score += 1
    return score
