# cogs/casino — ShadowSyn AAA VIP Casino package

from .cog import CasinoCog


def setup(bot):
    bot.add_cog(CasinoCog(bot))
