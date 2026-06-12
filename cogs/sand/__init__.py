# cogs/sand — ShadowSyn SAND: Raiders of Sophie guide package

from .guide import setup as _setup_guide
from .guides_funnel import setup as _setup_guides_funnel


def setup(bot):
    _setup_guide(bot)
    _setup_guides_funnel(bot)


__all__ = ["setup"]
