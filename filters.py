def get_flagged_users():
    return ["123456789012345678", "987654321098765432"]

def ai_flag_user(member):
    score = 0
    if not member.avatar:
        score += 2
    if member.name.lower().count("nitro") > 0 or "free" in member.name.lower():
        score += 3
    if len(member.roles) <= 1:
        score += 1
    if score >= 4:
        return True
    return False
